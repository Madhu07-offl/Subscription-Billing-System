import uuid
from datetime import date, datetime

from app.schemas.common import CamelModel, Money, PageMeta
from app.schemas.invoices import InvoiceSummaryOut
from app.schemas.subscriptions import CustomerRef


class BillingRunRequest(CamelModel):
    as_of: date | None = None
    subscription_ids: list[uuid.UUID] | None = None
    dry_run: bool = False


class DueSubscriptionOut(CamelModel):
    subscription_id: uuid.UUID
    number: str
    customer: CustomerRef
    next_billing_date: date
    estimated_total: Money


class DueSubscriptionList(CamelModel):
    data: list[DueSubscriptionOut]
    meta: PageMeta


class RunCounts(CamelModel):
    due: int
    created: int
    already_billed: int
    failed: int


class RunFailure(CamelModel):
    subscription_id: uuid.UUID
    number: str
    reason: str


class BillingRunResult(CamelModel):
    run_id: uuid.UUID
    as_of: date
    dry_run: bool
    counts: RunCounts
    created: list[InvoiceSummaryOut]
    failed: list[RunFailure]


class BillingRunSummary(CamelModel):
    run_id: uuid.UUID
    as_of: date
    started_by: uuid.UUID | None  # null = scheduled job
    started_at: datetime
    counts: RunCounts


class BillingRunList(CamelModel):
    data: list[BillingRunSummary]
    meta: PageMeta


class BillingRunDetail(BillingRunSummary):
    created: list[InvoiceSummaryOut]
    failed: list[RunFailure]


class AutoCloseRequest(CamelModel):
    as_of: date | None = None


class ClosedSubscription(CamelModel):
    subscription_id: uuid.UUID
    number: str


class AutoCloseResult(CamelModel):
    as_of: date
    closed_count: int
    closed: list[ClosedSubscription]
