"""The billing run (API.md section 3, rule 8).

One transaction per subscription: it either gets every invoice it owes or none, and a failure never blocks the
others. Missed periods are caught up in a loop (one invoice per period) but a period must start strictly before
expiry_date (exclusive). A unique-index violation on (subscription, period start) means the period is already billed: counted
as alreadyBilled, not failed. A dry run executes the very same code and rolls back, so what it reports is exactly
what a real run would create.
"""
import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.billing import BillingRun, Invoice, InvoiceLine
from app.models.catalogue import Plan
from app.models.identity import User
from app.models.subscriptions import Subscription
from app.schemas.billing import (
    BillingRunDetail,
    BillingRunRequest,
    BillingRunResult,
    BillingRunSummary,
    DueSubscriptionOut,
    RunCounts,
    RunFailure,
)
from app.schemas.invoices import InvoiceSummaryOut
from app.services import invoice_service, pricing
from app.services.periods import add_period
from app.services.subscription_service import v, v_subscriptions

logger = logging.getLogger("app.billing")

PERIOD_INDEX = "uq_invoices_subscription_period"


def _is_billable(sub: Subscription, as_of: date) -> bool:
    return (
        sub.status == "active"
        and not sub.is_paused
        and sub.next_billing_date is not None
        and sub.next_billing_date <= as_of
        and sub.expiry_date is not None
        and sub.next_billing_date < sub.expiry_date  # a period must start strictly before expiry
    )


# ------------------------------------------------------------------ preview
def list_due(db: Session, as_of: date | None, params: PageParams):
    """Active, non-paused subscriptions due on `as_of` whose current period has no live invoice yet."""
    as_of = as_of or date.today()
    already = exists().where(
        Invoice.subscription_id == v.id, Invoice.period_start == v.next_billing_date, Invoice.status != "cancelled"
    )
    stmt = select(v_subscriptions).where(
        v.status == "active",
        v.is_paused.is_(False),
        v.next_billing_date <= as_of,
        v.next_billing_date < v.expiry_date,
        ~already,
    )
    rows, meta = paginate(db, stmt.order_by(v.next_billing_date, v.number), params)
    items = [
        DueSubscriptionOut.model_validate(
            {
                "subscription_id": r.id,
                "number": r.number,
                "customer": {"id": r.customer_id, "name": r.customer_name, "email": r.customer_email},
                "next_billing_date": r.next_billing_date,
                "estimated_total": r.total,
            }
        )
        for r in rows
    ]
    return items, meta


# ------------------------------------------------------------------ one invoice
def _create_invoice(
    db: Session, sub: Subscription, period_start: date, period_end: date, run_id: uuid.UUID | None, user_id: uuid.UUID | None
) -> Invoice:
    """Price the subscription lines for one period and insert the draft invoice plus its discount usages."""
    discounts = pricing.load_candidate_discounts(db, period_start, lock=True)
    priced, totals = pricing.price_invoice(
        invoice_service.drafts_for(db, sub.lines), discounts, sub.id, period_start
    )
    inv = Invoice(
        subscription_id=sub.id,
        customer_id=sub.customer_id,
        billing_run_id=run_id,
        period_start=period_start,
        period_end=period_end,
        subtotal=totals.subtotal,
        discount_total=totals.discount_total,
        tax_total=totals.tax_total,
        total=totals.total,
        created_by=user_id,
        lines=[
            InvoiceLine(
                product_id=ln.product_id,
                description=f"{ln.product_name} ({ln.variant_label})" if ln.variant_label else ln.product_name,
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                discount_id=p.discount.discount_id if p.discount else None,
                discount_name=p.discount.name if p.discount else None,
                discount_amount=p.discount_amount,
                tax_id=ln.tax_id,
                tax_name=ln.tax_name,
                tax_rate=ln.tax_rate,
                tax_amount=p.tax_amount,
                sort_order=i,
            )
            for i, (ln, p) in enumerate(zip(sub.lines, priced))
        ],
    )
    db.add(inv)
    db.flush()  # the DB fills number and the billing_* customer snapshot; a duplicate period fails here
    invoice_service.sync_discount_usages(db, inv.id, {p.discount.discount_id for p in priced if p.discount})
    return inv


def _is_period_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return PERIOD_INDEX in {getattr(diag, "constraint_name", None)} or PERIOD_INDEX in str(exc.orig)


def _reason(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    text = str(getattr(exc, "orig", None) or exc).strip().splitlines()
    return (text[0] if text else type(exc).__name__)[:300]


# ------------------------------------------------------------------ one subscription
def _bill_subscription(
    db: Session,
    sub_id: uuid.UUID,
    number: str,
    as_of: date,
    run_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    dry_run: bool,
) -> tuple[list[InvoiceSummaryOut], int, RunFailure | None]:
    """Returns (invoices created, periods already billed, failure). Commits (or rolls back for a dry run)."""
    created_ids: list[uuid.UUID] = []
    already_billed = 0
    try:
        sub = db.scalars(
            select(Subscription)
            .where(Subscription.id == sub_id)
            .with_for_update(skip_locked=True)  # another run is on it: leave it to them
            .execution_options(populate_existing=True)
        ).first()
        if sub is None or not _is_billable(sub, as_of):
            db.rollback()
            return [], 0, None
        plan = db.get(Plan, sub.plan_id)
        while _is_billable(sub, as_of):
            period_start = sub.next_billing_date
            next_start = add_period(period_start, plan.billing_period)
            try:
                with db.begin_nested():  # a duplicate period must not poison the rest of the subscription
                    inv = _create_invoice(db, sub, period_start, next_start - timedelta(days=1), run_id, user_id)
                created_ids.append(inv.id)
            except IntegrityError as exc:
                if not _is_period_conflict(exc):
                    raise
                already_billed += 1
            sub.next_billing_date = next_start  # one billing period per invoice
        db.flush()
        created = invoice_service.summaries(db, created_ids)
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return created, already_billed, None
    except Exception as exc:  # noqa: BLE001 - one subscription's failure is reported, never raised
        db.rollback()
        logger.warning("Billing failed for %s: %s", number, exc)
        return [], 0, RunFailure(subscription_id=sub_id, number=number, reason=_reason(exc))


# ------------------------------------------------------------------ the run
def run_billing(db: Session, body: BillingRunRequest | None, user: User) -> BillingRunResult:
    body = body or BillingRunRequest()
    as_of = body.as_of or date.today()
    dry_run = body.dry_run

    stmt = select(Subscription.id, Subscription.number).where(
        Subscription.status == "active",
        Subscription.is_paused.is_(False),
        Subscription.next_billing_date <= as_of,
        Subscription.next_billing_date < Subscription.expiry_date,
    )
    if body.subscription_ids is not None:
        stmt = stmt.where(Subscription.id.in_(body.subscription_ids))
    candidates = db.execute(stmt.order_by(Subscription.next_billing_date, Subscription.number)).all()
    db.rollback()  # end the read transaction; each subscription gets its own

    run_id: uuid.UUID | None = None
    if not dry_run:
        run = BillingRun(as_of=as_of, dry_run=False, due_count=len(candidates), triggered_by=user.id)
        db.add(run)
        db.commit()  # committed first: invoices reference it
        run_id = run.id

    created: list[InvoiceSummaryOut] = []
    already_billed = 0
    failed: list[RunFailure] = []
    for sub_id, number in candidates:
        got, already, failure = _bill_subscription(db, sub_id, number, as_of, run_id, user.id, dry_run)
        created += got
        already_billed += already
        if failure:
            failed.append(failure)

    counts = RunCounts(due=len(candidates), created=len(created), already_billed=already_billed, failed=len(failed))
    if run_id is not None:
        run = db.get(BillingRun, run_id)
        run.created_count, run.already_billed, run.failed_count = counts.created, counts.already_billed, counts.failed
        run.failures = [f.model_dump(mode="json", by_alias=True) for f in failed]
        run.finished_at = func.now()  # the DB clock: started_at came from it, and finished_at >= started_at is a CHECK
        db.commit()
    return BillingRunResult(
        run_id=run_id or uuid.uuid4(),  # a dry run is not stored; its id only satisfies the response shape
        as_of=as_of,
        dry_run=dry_run,
        counts=counts,
        created=created,
        failed=failed,
    )


# ------------------------------------------------------------------ history
def _summary(run: BillingRun) -> dict:
    return {
        "run_id": run.id,
        "as_of": run.as_of,
        "started_by": run.triggered_by,
        "started_at": run.started_at,
        "counts": {
            "due": run.due_count,
            "created": run.created_count,
            "already_billed": run.already_billed,
            "failed": run.failed_count,
        },
    }


def list_runs(db: Session, params: PageParams):
    stmt = select(BillingRun).where(BillingRun.dry_run.is_(False)).order_by(BillingRun.started_at.desc(), BillingRun.id)
    runs, meta = paginate(db, stmt, params)
    return [BillingRunSummary.model_validate(_summary(r)) for r in runs], meta


def get_run(db: Session, run_id: uuid.UUID) -> BillingRunDetail:
    run = db.get(BillingRun, run_id)
    if run is None or run.dry_run:
        raise AppError.not_found("Billing run not found")
    ids = list(
        db.scalars(select(Invoice.id).where(Invoice.billing_run_id == run.id).order_by(Invoice.created_at, Invoice.number))
    )
    return BillingRunDetail.model_validate(
        {**_summary(run), "created": invoice_service.summaries(db, ids), "failed": run.failures or []}
    )
