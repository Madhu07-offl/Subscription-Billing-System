"""Invoices: reads (through v_invoices), draft correction, confirm, cancel and send (API.md sections 2 and 3).

amount_due / is_overdue come from the view, never from code. amount_paid and the confirmed <-> paid transition
belong to the payments trigger, so nothing here writes them. Every state change locks the invoice row first.
"""
import logging
import uuid
from collections.abc import Collection, Sequence
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import column, func, or_, select, table
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.billing import Invoice, InvoiceLine, Payment
from app.models.catalogue import Tax
from app.models.discounts import DiscountUsage
from app.models.identity import User
from app.models.subscriptions import Subscription
from app.schemas.invoices import InvoiceOut, InvoiceSummaryOut, InvoiceUpdate, SendInvoiceRequest
from app.services import payment_service, pricing

logger = logging.getLogger("app.invoices")

PAYMENT_TERM_DAYS = {"immediate": 0, "net_15": 15, "net_30": 30, "net_45": 45, "net_60": 60}

v_invoices = table(
    "v_invoices",
    *(
        column(c)
        for c in (
            "id", "number", "status", "subscription_id", "subscription_number", "customer_id", "customer_name",
            "customer_email", "billing_name", "billing_email", "billing_company", "billing_address",
            "billing_run_id", "period_start", "period_end", "issue_date", "due_date", "subtotal", "discount_total",
            "tax_total", "total", "amount_paid", "amount_due", "is_overdue", "sent_at", "notes", "created_by",
            "created_at", "updated_at",
        )
    ),
)
v = v_invoices.c


# ------------------------------------------------------------------ reads
def _summary_dict(r) -> dict:
    return {
        "id": r.id,
        "number": r.number,
        "status": r.status,
        "subscription_id": r.subscription_id,
        "subscription_number": r.subscription_number,
        "customer": {"id": r.customer_id, "name": r.customer_name, "email": r.customer_email},
        "period_start": r.period_start,
        "period_end": r.period_end,
        "issue_date": r.issue_date,
        "due_date": r.due_date,
        "subtotal": r.subtotal,
        "discount_total": r.discount_total,
        "tax_total": r.tax_total,
        "total": r.total,
        "amount_paid": r.amount_paid,
        "amount_due": r.amount_due,
        "is_overdue": r.is_overdue,
        "sent_at": r.sent_at,
        "created_at": r.created_at,
    }


def summaries(db: Session, ids: Sequence[uuid.UUID]) -> list[InvoiceSummaryOut]:
    """Summaries for these invoice ids, in the order given."""
    if not ids:
        return []
    rows = {r.id: r for r in db.execute(select(v_invoices).where(v.id.in_(list(ids))))}
    return [InvoiceSummaryOut.model_validate(_summary_dict(rows[i])) for i in ids if i in rows]


def _customer_details(r) -> dict:
    snapshot = dict(r.billing_address or {})
    tax_id = snapshot.pop("taxId", None)
    return {
        "name": r.billing_name,
        "email": r.billing_email,
        "company": r.billing_company,
        "tax_id": tax_id,
        "address": snapshot or None,
    }


def get_invoice(db: Session, invoice_id: uuid.UUID, user: User) -> InvoiceOut:
    stmt = select(v_invoices).where(v.id == invoice_id)
    if user.role == "customer":
        stmt = stmt.where(v.customer_id == user.customer_id, v.status != "draft")  # someone else's, or a draft: 404
    r = db.execute(stmt).first()
    if r is None:
        raise AppError.not_found("Invoice not found")
    lines = list(
        db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == r.id).order_by(InvoiceLine.sort_order, InvoiceLine.id))
    )
    payments = payment_service.payments_of_invoice(db, r.id)
    return InvoiceOut.model_validate(
        {
            **_summary_dict(r),
            "lines": lines,
            "payments": payments,
            "customer_details": _customer_details(r),
            "notes": r.notes,
        }
    )


def list_invoices(
    db: Session,
    user: User,
    params: PageParams,
    *,
    q: str | None = None,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    subscription_id: uuid.UUID | None = None,
    is_overdue: bool | None = None,
    has_balance: bool | None = None,
    issued_from: date | None = None,
    issued_to: date | None = None,
):
    stmt = select(v_invoices)
    if user.role == "customer":
        stmt = stmt.where(v.customer_id == user.customer_id, v.status != "draft")  # customers never see drafts
    elif customer_id is not None:
        stmt = stmt.where(v.customer_id == customer_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(v.number.ilike(like), v.subscription_number.ilike(like), v.customer_name.ilike(like), v.customer_email.ilike(like))
        )
    if status:
        stmt = stmt.where(v.status == status)
    if subscription_id is not None:
        stmt = stmt.where(v.subscription_id == subscription_id)
    if is_overdue is not None:
        stmt = stmt.where(v.is_overdue.is_(is_overdue))
    if has_balance is not None:
        stmt = stmt.where(v.amount_due > 0 if has_balance else v.amount_due <= 0)
    if issued_from is not None:
        stmt = stmt.where(v.issue_date >= issued_from)
    if issued_to is not None:
        stmt = stmt.where(v.issue_date <= issued_to)
    rows, meta = paginate(db, stmt.order_by(v.created_at.desc(), v.number.desc()), params)
    return [InvoiceSummaryOut.model_validate(_summary_dict(r)) for r in rows], meta


def list_for_subscription(db: Session, subscription_id: uuid.UUID, user: User, params: PageParams):
    sub_stmt = select(Subscription.id).where(Subscription.id == subscription_id)
    if user.role == "customer":
        sub_stmt = sub_stmt.where(Subscription.customer_id == user.customer_id)
    if db.scalar(sub_stmt) is None:
        raise AppError.not_found("Subscription not found")
    return list_invoices(db, user, params, subscription_id=subscription_id)


# ------------------------------------------------------------------ discount usage ledger
def sync_discount_usages(db: Session, invoice_id: uuid.UUID, applied: Collection[uuid.UUID]) -> None:
    """Make discount_usages match the discounts the invoice now uses. Only the ledger is touched: the DB
    trigger turns inserts / released_at changes into discounts.used_count, which code never writes."""
    wanted = set(applied)
    existing = {u.discount_id: u for u in db.scalars(select(DiscountUsage).where(DiscountUsage.invoice_id == invoice_id))}
    for discount_id, usage in existing.items():
        if discount_id in wanted and usage.released_at is not None:
            usage.released_at = None  # applies again
        elif discount_id not in wanted and usage.released_at is None:
            usage.released_at = func.now()
    for discount_id in wanted - existing.keys():
        db.add(DiscountUsage(discount_id=discount_id, invoice_id=invoice_id))
    db.flush()


# ------------------------------------------------------------------ writes
def _find_locked(db: Session, invoice_id: uuid.UUID) -> Invoice:
    inv = db.scalars(select(Invoice).where(Invoice.id == invoice_id).with_for_update()).first()
    if inv is None:
        raise AppError.not_found("Invoice not found")
    return inv


def drafts_for(db: Session, lines: Sequence) -> list[pricing.InvoiceLineDraft]:
    """Price inputs for subscription or invoice lines. The tax rate is the line's snapshot; only the way it is
    computed (percentage | fixed) is looked up from the tax row."""
    tax_ids = {ln.tax_id for ln in lines if ln.tax_id}
    computation = {t.id: t.computation for t in db.scalars(select(Tax).where(Tax.id.in_(tax_ids)))} if tax_ids else {}
    return [
        pricing.InvoiceLineDraft(
            ln.product_id, ln.quantity, ln.unit_price, computation.get(ln.tax_id) if ln.tax_id else None, ln.tax_rate
        )
        for ln in lines
    ]


def reprice(db: Session, inv: Invoice) -> None:
    """Recompute discounts, tax and totals of a draft from its current lines (rules 5-7)."""
    drafts = drafts_for(db, inv.lines)
    held = set(
        db.scalars(
            select(DiscountUsage.discount_id).where(DiscountUsage.invoice_id == inv.id, DiscountUsage.released_at.is_(None))
        )
    )
    discounts = pricing.load_candidate_discounts(db, inv.period_start, lock=True)
    priced, totals = pricing.price_invoice(drafts, discounts, inv.subscription_id, inv.period_start, held)
    for ln, p in zip(inv.lines, priced):
        ln.discount_id = p.discount.discount_id if p.discount else None
        ln.discount_name = p.discount.name if p.discount else None
        ln.discount_amount = p.discount_amount
        ln.tax_amount = p.tax_amount
    inv.subtotal, inv.discount_total, inv.tax_total, inv.total = (
        totals.subtotal, totals.discount_total, totals.tax_total, totals.total,
    )
    db.flush()
    sync_discount_usages(db, inv.id, {p.discount.discount_id for p in priced if p.discount})


def update_invoice(db: Session, invoice_id: uuid.UUID, body: InvoiceUpdate, user: User) -> InvoiceOut:
    inv = _find_locked(db, invoice_id)
    if inv.status != "draft":
        raise AppError.conflict(f"A {inv.status} invoice can no longer be edited; cancel it and let billing recreate it")
    sent = body.model_fields_set
    if "notes" in sent:
        inv.notes = body.notes
    if body.lines:
        by_id = {ln.id: ln for ln in inv.lines}
        for i, change in enumerate(body.lines):
            line = by_id.get(change.id)
            if line is None:
                raise AppError.validation("Line does not belong to this invoice", f"lines.{i}.id")
            if change.description is not None:
                line.description = change.description
            if change.quantity is not None:
                line.quantity = change.quantity
            if change.unit_price is not None:
                line.unit_price = pricing.money(change.unit_price)
        reprice(db, inv)
    db.commit()
    return get_invoice(db, inv.id, user)


def confirm(db: Session, invoice_id: uuid.UUID, user: User) -> InvoiceOut:
    inv = _find_locked(db, invoice_id)
    if inv.status != "draft":
        raise AppError.conflict(f"Cannot confirm: invoice is {inv.status}, expected draft")
    terms = db.scalar(select(Subscription.payment_terms).where(Subscription.id == inv.subscription_id))
    today = date.today()
    inv.issue_date = today
    inv.due_date = today + timedelta(days=PAYMENT_TERM_DAYS.get(terms or "immediate", 0))
    inv.status = "confirmed"
    db.commit()
    return get_invoice(db, inv.id, user)


def cancel(db: Session, invoice_id: uuid.UUID, user: User) -> InvoiceOut:
    inv = _find_locked(db, invoice_id)
    if inv.status == "cancelled":
        raise AppError.conflict("Invoice is already cancelled")
    has_payment = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.invoice_id == inv.id, Payment.is_voided.is_(False))
    )
    if has_payment:
        raise AppError.business_rule("An invoice with payments cannot be cancelled; void the payments first")
    if inv.status not in ("draft", "confirmed"):
        raise AppError.conflict(f"Cannot cancel an invoice that is {inv.status}")

    sub = db.scalars(select(Subscription).where(Subscription.id == inv.subscription_id).with_for_update()).first()
    inv.status = "cancelled"  # trg_invoices_release_discounts gives the discount usage back
    db.flush()
    # Only the subscription's latest invoice rewinds the billing date, so that period is billed again.
    later = db.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.subscription_id == inv.subscription_id,
            Invoice.id != inv.id,
            Invoice.status != "cancelled",
            Invoice.period_start > inv.period_start,
        )
    )
    if later == 0 and sub is not None and sub.status == "active":
        sub.next_billing_date = min(sub.next_billing_date or inv.period_start, inv.period_start)
    db.commit()
    return get_invoice(db, inv.id, user)


def send(db: Session, invoice_id: uuid.UUID, body: SendInvoiceRequest | None, user: User) -> InvoiceOut:
    inv = _find_locked(db, invoice_id)
    if inv.status not in ("confirmed", "paid"):
        raise AppError.conflict(f"Cannot send: invoice is {inv.status}, expected confirmed or paid")
    to = (body.to if body and body.to else None) or inv.billing_email
    logger.info(
        "EMAIL (console stub) to=%s subject='Invoice %s' total=%s due=%s message=%r",
        to, inv.number, inv.total, inv.due_date, body.message if body else None,
    )
    inv.sent_at = datetime.now(timezone.utc)
    db.commit()
    return get_invoice(db, inv.id, user)
