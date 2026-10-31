import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel, Money, PageMeta

SubscriptionStatus = Literal["draft", "quotation", "confirmed", "active", "closed"]
PaymentTerms = Literal["immediate", "net_15", "net_30", "net_45", "net_60"]
BillingPeriod = Literal["daily", "weekly", "monthly", "yearly"]


class LineInput(CamelModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(ge=1)
    unit_price: Money | None = Field(default=None, ge=0)  # optional override


class RequestLine(CamelModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(ge=1)


class SubscriptionInput(CamelModel):
    customer_id: uuid.UUID
    template_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    start_date: date | None = None
    expiry_date: date | None = None
    payment_terms: PaymentTerms | None = None
    lines: list[LineInput] | None = None
    notes: str | None = None


class SubscriptionUpdate(CamelModel):
    """Partial body: only fields that are sent are changed. Explicit null is rejected (no nullable fields)."""

    customer_id: uuid.UUID = None  # type: ignore[assignment]
    plan_id: uuid.UUID = None  # type: ignore[assignment]
    start_date: date = None  # type: ignore[assignment]
    expiry_date: date = None  # type: ignore[assignment]
    payment_terms: PaymentTerms = None  # type: ignore[assignment]
    lines: list[LineInput] = None  # type: ignore[assignment]
    notes: str = None  # type: ignore[assignment]


class SubscriptionRequest(CamelModel):
    plan_id: uuid.UUID
    start_date: date
    lines: list[RequestLine] = Field(min_length=1)
    notes: str | None = None


class CloseRequest(CamelModel):
    reason: str | None = None


class RenewRequest(CamelModel):
    new_expiry_date: date | None = None


class CustomerRef(CamelModel):
    id: uuid.UUID
    name: str
    email: str


class PlanRef(CamelModel):
    id: uuid.UUID
    name: str
    billing_period: BillingPeriod
    allow_early_close: bool
    allow_pause: bool
    allow_renew: bool


class SubscriptionLineOut(CamelModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    variant_id: uuid.UUID | None
    variant_label: str | None
    quantity: int
    unit_price: Money
    tax_id: uuid.UUID | None
    tax_name: str | None
    tax_rate: float | None
    tax_amount: Money
    amount: Money


class SubscriptionOut(CamelModel):
    id: uuid.UUID
    number: str
    status: SubscriptionStatus
    is_paused: bool
    customer: CustomerRef
    plan: PlanRef | None
    template_id: uuid.UUID | None
    start_date: date | None
    expiry_date: date | None
    payment_terms: PaymentTerms | None
    quotation_valid_until: date | None
    next_billing_date: date | None
    lines: list[SubscriptionLineOut]
    subtotal: Money
    tax_total: Money
    total: Money
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    closed_at: datetime | None
    close_reason: str | None


class SubscriptionList(CamelModel):
    data: list[SubscriptionOut]
    meta: PageMeta


class UserRef(CamelModel):
    id: uuid.UUID
    name: str


class StatusChangeOut(CamelModel):
    id: uuid.UUID
    event: Literal["created", "status_change", "paused", "resumed", "renewed"]
    from_status: SubscriptionStatus | None
    to_status: SubscriptionStatus
    changed_by: UserRef | None
    reason: str | None
    created_at: datetime


class StatusChangeList(CamelModel):
    data: list[StatusChangeOut]
    meta: PageMeta
