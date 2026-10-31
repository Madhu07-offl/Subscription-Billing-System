from datetime import date
from typing import Literal

from app.schemas.common import CamelModel, Money

PaymentMethod = Literal["cash", "bank_transfer", "card", "upi", "cheque", "other"]
GroupBy = Literal["day", "week", "month"]


class SubscriptionCounts(CamelModel):
    active: int
    by_status: dict[str, int]


class OverdueTotals(CamelModel):
    count: int
    amount: Money


class MethodTotals(CamelModel):
    method: PaymentMethod
    count: int
    amount: Money


class DashboardSummary(CamelModel):
    period: dict[str, date]
    subscriptions: SubscriptionCounts
    mrr: Money
    revenue_invoiced: Money
    revenue_collected: Money
    outstanding: Money
    overdue: OverdueTotals
    invoices_by_status: dict[str, int]
    payments_by_method: list[MethodTotals]


class RevenuePoint(CamelModel):
    period: date
    invoiced: Money
    collected: Money


class RevenueSeries(CamelModel):
    data: list[RevenuePoint]
