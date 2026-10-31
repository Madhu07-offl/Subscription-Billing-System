"""Payments (API.md rule 9).

invoices.amount_paid and the confirmed <-> paid transition are maintained by trg_payments_sync_invoice, so this
module never writes them: it inserts a payment, or voids one by setting voided_at / voided_by, and the trigger
recomputes the invoice in the same transaction. The invoice row is locked first so concurrent payments are checked
against the balance one after another.
"""
import uuid
from datetime import date
from typing import Any

from sqlalchemy import Numeric, Uuid, column, func, select, table
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.billing import Invoice, Payment
from app.models.identity import Customer, User
from app.schemas.invoices import PaymentInput, PaymentOut

# amount_due is defined once, in v_invoices (invoice_service imports this module, so it cannot be imported back).
_v_invoices = table("v_invoices", column("id", Uuid), column("amount_due", Numeric(12, 2)))

_COLUMNS = (
    Payment,
    Invoice.number.label("invoice_number"),
    Customer.id.label("cust_id"),
    Customer.name.label("cust_name"),
    Customer.email.label("cust_email"),
)


def payment_select():
    """SELECT payment + the invoice number + the (live) customer, ready to filter."""
    return (
        select(*_COLUMNS)
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(Customer, Customer.id == Invoice.customer_id)
    )


def to_out(row: Any) -> PaymentOut:
    p: Payment = row.Payment
    return PaymentOut.model_validate(
        {
            "id": p.id,
            "invoice_id": p.invoice_id,
            "invoice_number": row.invoice_number,
            "customer": {"id": row.cust_id, "name": row.cust_name, "email": row.cust_email},
            "method": p.method,
            "amount": p.amount,
            "payment_date": p.payment_date,
            "reference": p.reference,
            "note": p.note,
            "is_voided": p.is_voided,
            "recorded_by": p.recorded_by,
            "created_at": p.created_at,
        }
    )


def payments_of_invoice(db: Session, invoice_id: uuid.UUID) -> list[PaymentOut]:
    """All payments of one invoice, voided ones included (they carry isVoided), oldest first."""
    rows = db.execute(
        payment_select().where(Payment.invoice_id == invoice_id).order_by(Payment.payment_date, Payment.created_at, Payment.id)
    ).all()
    return [to_out(r) for r in rows]


def _scoped(stmt, user: User):
    """A customer only ever sees payments on their own invoices; anything else is a 404."""
    if user.role == "customer":
        stmt = stmt.where(Invoice.customer_id == user.customer_id)
    return stmt


def get_payment(db: Session, payment_id: uuid.UUID, user: User) -> PaymentOut:
    row = db.execute(_scoped(payment_select().where(Payment.id == payment_id), user)).first()
    if row is None:
        raise AppError.not_found("Payment not found")
    return to_out(row)


def list_payments(
    db: Session,
    user: User,
    params: PageParams,
    *,
    invoice_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    method: str | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
):
    stmt = _scoped(payment_select(), user)
    if invoice_id is not None:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if customer_id is not None and user.role != "customer":
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if method:
        stmt = stmt.where(Payment.method == method)
    if paid_from is not None:
        stmt = stmt.where(Payment.payment_date >= paid_from)
    if paid_to is not None:
        stmt = stmt.where(Payment.payment_date <= paid_to)
    rows, meta = paginate(db, stmt.order_by(Payment.payment_date.desc(), Payment.created_at.desc(), Payment.id), params)
    return [to_out(r) for r in rows], meta


def record_payment(db: Session, body: PaymentInput, user: User) -> PaymentOut:
    inv = db.scalars(select(Invoice).where(Invoice.id == body.invoice_id).with_for_update()).first()
    if inv is None:
        raise AppError.validation("Invoice not found", "invoiceId")
    if inv.status != "confirmed":
        raise AppError.business_rule(
            f"Payments can only be recorded on confirmed invoices (invoice is {inv.status})",
            [{"field": "invoiceId", "message": f"Invoice is {inv.status}"}],
        )
    if body.payment_date > date.today():
        raise AppError.business_rule(
            "paymentDate cannot be in the future", [{"field": "paymentDate", "message": "Cannot be in the future"}]
        )
    amount = body.amount
    if amount.as_tuple().exponent < -2:
        raise AppError.validation("amount can have at most 2 decimals", "amount")
    amount_due = db.scalar(select(_v_invoices.c.amount_due).where(_v_invoices.c.id == inv.id))
    if amount <= 0:
        raise AppError.business_rule("amount must be greater than 0", [{"field": "amount", "message": "Must be > 0"}])
    if amount > amount_due:
        raise AppError.business_rule(
            f"amount {amount:.2f} exceeds the amount due {amount_due:.2f}",
            [{"field": "amount", "message": f"At most {amount_due:.2f}"}],
        )
    payment = Payment(
        invoice_id=inv.id,
        method=body.method,
        amount=amount,
        payment_date=body.payment_date,
        reference=body.reference,
        note=body.note,
        recorded_by=user.id,
    )
    db.add(payment)
    db.flush()  # trg_payments_sync_invoice updates amount_paid and flips confirmed -> paid here
    db.commit()
    return get_payment(db, payment.id, user)


def void_payment(db: Session, payment_id: uuid.UUID, user: User) -> None:
    invoice_id = db.scalar(select(Payment.invoice_id).where(Payment.id == payment_id))
    if invoice_id is None:
        raise AppError.not_found("Payment not found")
    db.scalars(select(Invoice).where(Invoice.id == invoice_id).with_for_update()).first()  # lock order: invoice first
    payment = db.scalars(select(Payment).where(Payment.id == payment_id).with_for_update()).first()
    if payment is None:
        raise AppError.not_found("Payment not found")
    if payment.voided_at is not None:
        raise AppError.conflict("Payment is already voided")
    payment.voided_at = func.now()  # is_voided is generated from it; the trigger recalculates the invoice
    payment.voided_by = user.id
    db.commit()
