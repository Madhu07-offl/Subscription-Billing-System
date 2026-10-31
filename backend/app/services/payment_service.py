"""Payments (API.md rule 9). Reads here; recording and voiding are added with the payment endpoints.

invoices.amount_paid and the confirmed <-> paid transition are maintained by trg_payments_sync_invoice, so this
module never writes them.
"""
import uuid
from typing import Any

from sqlalchemy import select

from app.models.billing import Invoice, Payment
from app.models.identity import Customer
from app.schemas.invoices import PaymentOut

_COLUMNS = (Payment, Invoice.number.label("invoice_number"), Customer.id.label("cust_id"),
            Customer.name.label("cust_name"), Customer.email.label("cust_email"))


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


def payments_of_invoice(db, invoice_id: uuid.UUID) -> list[PaymentOut]:
    """All payments of one invoice, voided ones included (they carry isVoided), oldest first."""
    rows = db.execute(
        payment_select().where(Payment.invoice_id == invoice_id).order_by(Payment.payment_date, Payment.created_at, Payment.id)
    ).all()
    return [to_out(r) for r in rows]
