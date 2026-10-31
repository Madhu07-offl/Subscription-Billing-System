import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, PlainSerializer, StringConstraints

from app.schemas.common import CamelModel, PageMeta
from app.schemas.products import ProductType

# The contract types tax/discount `value` as a plain JSON number (a percent such as 18, or a fixed amount),
# unlike money fields which are strings. Stored as numeric(12,4); sent as a number.
Number = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
Amount = Annotated[Number, Field(ge=0, max_digits=12, decimal_places=4)]

Computation = Literal["percentage", "fixed"]
TaxName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TaxInput(CamelModel):
    name: TaxName
    computation: Computation
    value: Amount
    applies_to_product_types: list[ProductType] = Field(default_factory=list)
    is_active: bool = True


class TaxUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    name: TaxName | None = None
    computation: Computation | None = None
    value: Amount | None = None
    applies_to_product_types: list[ProductType] | None = None
    is_active: bool | None = None


class TaxOut(CamelModel):
    id: uuid.UUID
    name: str
    computation: Computation
    value: Number
    applies_to_product_types: list[ProductType]
    is_active: bool


class TaxList(CamelModel):
    data: list[TaxOut]
    meta: PageMeta
