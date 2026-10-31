"""Finance dashboard data (contract: Reports tag, API.md rule 10). Read-only: every figure comes from the
v_report_* views and v_invoices, so amount due, overdue and MRR are defined in exactly one place (the database).

Point-in-time figures (subscription and invoice counts, MRR, outstanding, overdue) are as of today and ignore
from/to; only revenueInvoiced, revenueCollected and paymentsByMethod use the period. planId / customerId narrow
every figure; an id that matches nothing simply yields zeros."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.schemas.reports import DashboardSummary, MethodTotals, OverdueTotals, RevenuePoint, SubscriptionCounts

SUBSCRIPTION_STATUSES = ("draft", "quotation", "confirmed", "active", "closed")
INVOICE_STATUSES = ("draft", "confirmed", "paid", "cancelled")
MAX_BUCKETS = 1000

# groupBy -> (date_trunc unit, step between buckets). Fixed strings, interpolated into SQL on purpose.
_GROUPS = {"day": ("day", "1 day"), "week": ("week", "1 week"), "month": ("month", "1 month")}

_PLAN = "(cast(:plan_id as uuid) is null or {plan} = cast(:plan_id as uuid))"
_CUSTOMER = "(cast(:customer_id as uuid) is null or {customer} = cast(:customer_id as uuid))"


def _filters(plan: str, customer: str) -> str:
    return f"{_PLAN.format(plan=plan)} and {_CUSTOMER.format(customer=customer)}"


def resolve_period(start: date | None, end: date | None) -> tuple[date, date]:
    today = date.today()
    start = start or today.replace(day=1)
    end = end or today
    if start > end:
        raise AppError.validation("from cannot be after to", field="from")
    return start, end


def summary(
    db: Session, start: date | None, end: date | None, plan_id: uuid.UUID | None, customer_id: uuid.UUID | None
) -> DashboardSummary:
    start, end = resolve_period(start, end)
    # One statement, one round trip: with a remote database (Supabase) latency, not row counts, is what eats
    # the 2 s budget. Money leaves SQL as text so it is never squeezed through a JSON float.
    sub_f, inv_f = _filters("s.plan_id", "s.customer_id"), _filters("s.plan_id", "i.customer_id")
    fact_f, mrr_f = _filters("f.plan_id", "f.customer_id"), _filters("m.plan_id", "m.customer_id")
    row = db.execute(
        text(
            f"""
            select
              (select coalesce(jsonb_object_agg(status, n), '{{}}') from (
                 select status, count(*)::int as n from subscriptions s where {sub_f} group by status) x) as sub_counts,
              (select coalesce(jsonb_object_agg(status, n), '{{}}') from (
                 select i.status, count(*)::int as n from invoices i join subscriptions s on s.id = i.subscription_id
                  where {inv_f} group by i.status) x) as invoice_counts,
              (select coalesce(sum(monthly_amount), 0)::text from v_report_mrr m where {mrr_f}) as mrr,
              (select jsonb_build_object(
                        'invoiced',  coalesce(sum(amount) filter (where kind = 'invoiced'), 0)::text,
                        'collected', coalesce(sum(amount) filter (where kind = 'collected'), 0)::text)
                 from v_report_revenue_facts f where f.day between :start and :end and {fact_f}) as revenue,
              (select coalesce(jsonb_agg(jsonb_build_object('method', method, 'count', n, 'amount', amt::text)
                                         order by amt desc, method), '[]') from (
                 select method, count(*)::int as n, sum(amount) as amt from v_report_revenue_facts f
                  where f.kind = 'collected' and f.day between :start and :end and {fact_f} group by method) y) as methods,
              (select jsonb_build_object(
                        'outstanding',    coalesce(sum(v.amount_due) filter (where v.status = 'confirmed'), 0)::text,
                        'overdue_count',  (count(*) filter (where v.is_overdue))::int,
                        'overdue_amount', coalesce(sum(v.amount_due) filter (where v.is_overdue), 0)::text)
                 from v_invoices v join subscriptions s on s.id = v.subscription_id
                where {_filters("s.plan_id", "v.customer_id")}) as owed
            """
        ),
        {"plan_id": plan_id, "customer_id": customer_id, "start": start, "end": end},
    ).one()

    sub_counts = {**dict.fromkeys(SUBSCRIPTION_STATUSES, 0), **row.sub_counts}
    invoice_counts = {**dict.fromkeys(INVOICE_STATUSES, 0), **row.invoice_counts}
    return DashboardSummary(
        period={"from": start, "to": end},
        subscriptions=SubscriptionCounts(active=sub_counts["active"], by_status=sub_counts),
        mrr=Decimal(row.mrr),
        revenue_invoiced=Decimal(row.revenue["invoiced"]),
        revenue_collected=Decimal(row.revenue["collected"]),
        outstanding=Decimal(row.owed["outstanding"]),
        overdue=OverdueTotals(count=row.owed["overdue_count"], amount=Decimal(row.owed["overdue_amount"])),
        invoices_by_status=invoice_counts,
        payments_by_method=[
            MethodTotals(method=m["method"], count=m["count"], amount=Decimal(m["amount"])) for m in row.methods
        ],
    )


def _bucket_count(start: date, end: date, group_by: str) -> int:
    if group_by == "day":
        return (end - start).days + 1
    if group_by == "week":
        first = start - timedelta(days=start.weekday())
        return (end - first).days // 7 + 1
    return (end.year - start.year) * 12 + end.month - start.month + 1


def revenue(
    db: Session,
    start: date | None,
    end: date | None,
    group_by: str,
    plan_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
) -> list[RevenuePoint]:
    """Invoiced (by issue date) vs collected (by payment date) per bucket. Empty buckets are returned as zeros
    so the chart has no gaps. Weeks start on Monday and `period` is the first day of the bucket."""
    start, end = resolve_period(start, end)
    if _bucket_count(start, end, group_by) > MAX_BUCKETS:
        raise AppError.validation(f"That range has more than {MAX_BUCKETS} {group_by}s; narrow it or group wider", field="from")
    unit, step = _GROUPS[group_by]
    rows = db.execute(
        text(
            f"select b.period::date, "
            f"       coalesce(sum(f.amount) filter (where f.kind = 'invoiced'), 0), "
            f"       coalesce(sum(f.amount) filter (where f.kind = 'collected'), 0) "
            f"from generate_series(date_trunc('{unit}', cast(:start as timestamp)), cast(:end as timestamp), "
            f"                     interval '{step}') as b(period) "
            f"left join v_report_revenue_facts f "
            f"  on date_trunc('{unit}', cast(f.day as timestamp)) = b.period "
            f" and f.day between :start and :end "
            f" and {_filters('f.plan_id', 'f.customer_id')} "
            f"group by b.period order by b.period"
        ),
        {"start": start, "end": end, "plan_id": plan_id, "customer_id": customer_id},
    ).all()
    return [RevenuePoint(period=period, invoiced=invoiced, collected=collected) for period, invoiced, collected in rows]
