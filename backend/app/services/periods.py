"""Billing-period arithmetic shared by renew and the billing run."""
import calendar
from datetime import date, timedelta


def add_months(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(d.day, calendar.monthrange(year, month + 1)[1]))


def add_period(d: date, billing_period: str) -> date:
    """d plus one plan term (daily | weekly | monthly | yearly)."""
    if billing_period == "daily":
        return d + timedelta(days=1)
    if billing_period == "weekly":
        return d + timedelta(weeks=1)
    if billing_period == "monthly":
        return add_months(d, 1)
    if billing_period == "yearly":
        return add_months(d, 12)
    raise ValueError(f"unknown billing period: {billing_period}")


def next_period_start(period_start: date, billing_period: str, anchor: date) -> date:
    """Start of the billing period after `period_start` for a subscription that started on `anchor`.

    Monthly and yearly periods keep the anchor's day of month (clamped in short months) whenever period_start sits
    on it, so a 31st start bills 31 Jan -> 28 Feb -> 31 Mar instead of drifting to the 28th for good. A period that
    resume moved off that day (nextBillingDate = today) keeps its own day, so every period is still a full term.
    """
    if billing_period not in ("monthly", "yearly"):
        return add_period(period_start, billing_period)
    on_anchor_day = period_start.day == min(anchor.day, calendar.monthrange(period_start.year, period_start.month)[1])
    day = anchor.day if on_anchor_day else period_start.day
    first = add_months(period_start.replace(day=1), 1 if billing_period == "monthly" else 12)
    return first.replace(day=min(day, calendar.monthrange(first.year, first.month)[1]))
