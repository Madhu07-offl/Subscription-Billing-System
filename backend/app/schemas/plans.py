import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import CamelModel, Money, PageMeta
from app.schemas.products import Price

BillingPeriod = Literal["daily", "weekly", "monthly", "yearly"]
PlanName = Annotated[str, Field(min_length=1, max_length=200)]


class PlanInput(CamelModel):
    name: PlanName
    price: Price
    billing_period: BillingPeriod
    min_quantity: int = Field(default=1, ge=1, le=1_000_000)
    available_from: date
    available_to: date | None = None
    auto_close: bool = False
    allow_early_close: bool = False
    allow_pause: bool = False
    allow_renew: bool = True
    is_active: bool = True


class PlanUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    name: PlanName | None = None
    price: Price | None = None
    billing_period: BillingPeriod | None = None
    min_quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    available_from: date | None = None
    available_to: date | None = None  # null is meaningful here: no end date
    auto_close: bool | None = None
    allow_early_close: bool | None = None
    allow_pause: bool | None = None
    allow_renew: bool | None = None
    is_active: bool | None = None


class PlanOut(CamelModel):
    id: uuid.UUID
    name: str
    price: Money
    billing_period: BillingPeriod
    min_quantity: int
    available_from: date
    available_to: date | None
    auto_close: bool
    allow_early_close: bool
    allow_pause: bool
    allow_renew: bool
    is_active: bool
    created_at: datetime


class PlanList(CamelModel):
    data: list[PlanOut]
    meta: PageMeta
