import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import CamelModel, Money, PageMeta
from app.schemas.products import Price
from app.schemas.taxes import Amount, Number

DiscountType = Literal["percentage", "fixed"]
DiscountScope = Literal["products", "subscriptions"]
DiscountStatus = Literal["scheduled", "running", "expired", "exhausted", "inactive"]
DiscountName = Annotated[str, Field(min_length=1, max_length=200)]
MinQuantity = Annotated[int, Field(ge=1, le=1_000_000)]
UsageLimit = Annotated[int, Field(ge=1, le=1_000_000_000)]


class DiscountInput(CamelModel):
    name: DiscountName
    type: DiscountType
    value: Amount
    scope: DiscountScope
    min_purchase_amount: Price | None = None
    min_quantity: MinQuantity | None = None
    start_date: date
    end_date: date | None = None
    usage_limit: UsageLimit | None = None
    product_ids: list[uuid.UUID] = Field(default_factory=list)
    subscription_ids: list[uuid.UUID] = Field(default_factory=list)
    is_active: bool = True


class DiscountUpdate(CamelModel):
    """Partial update: only fields present in the body are applied. usedCount is database-owned and ignored."""

    name: DiscountName | None = None
    type: DiscountType | None = None
    value: Amount | None = None
    scope: DiscountScope | None = None
    min_purchase_amount: Price | None = None
    min_quantity: MinQuantity | None = None
    start_date: date | None = None
    end_date: date | None = None
    usage_limit: UsageLimit | None = None
    product_ids: list[uuid.UUID] | None = None
    subscription_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None


class DiscountOut(CamelModel):
    id: uuid.UUID
    name: str
    type: DiscountType
    value: Number
    scope: DiscountScope
    min_purchase_amount: Money | None
    min_quantity: int | None
    start_date: date
    end_date: date | None
    usage_limit: int | None
    used_count: int
    status: DiscountStatus
    product_ids: list[uuid.UUID]
    subscription_ids: list[uuid.UUID]
    is_active: bool


class DiscountList(CamelModel):
    data: list[DiscountOut]
    meta: PageMeta
