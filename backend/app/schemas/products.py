import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, Money, PageMeta

ProductType = Literal["software", "addon", "service", "goods"]

# numeric(12,2), non-negative, at most two decimals. Accepts "560.00" or 560.
Price = Annotated[Money, Field(ge=0, max_digits=12, decimal_places=2)]
# Stripped before the length check, so a blank name/attribute/value is a 400 instead of failing the database CHECK.
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class VariantInput(CamelModel):
    attribute: Text200
    value: Text200
    extra_price: Price


class VariantUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    attribute: Text200 | None = None
    value: Text200 | None = None
    extra_price: Price | None = None


class VariantOut(CamelModel):
    id: uuid.UUID
    product_id: uuid.UUID
    attribute: str
    value: str
    extra_price: Money
    is_archived: bool


class ProductInput(CamelModel):
    name: Text200
    type: ProductType
    sales_price: Price
    cost_price: Price
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    variants: list[VariantInput] = Field(default_factory=list)


class ProductUpdate(CamelModel):
    """Partial update. Variants are managed through /products/{id}/variants, so they are not accepted here."""

    name: Text200 | None = None
    type: ProductType | None = None
    sales_price: Price | None = None
    cost_price: Price | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ProductOut(CamelModel):
    id: uuid.UUID
    name: str
    type: ProductType
    sales_price: Money
    cost_price: Money
    notes: str | None
    is_active: bool
    variants: list[VariantOut]
    created_at: datetime


class ProductList(CamelModel):
    data: list[ProductOut]
    meta: PageMeta
