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
