import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, ForeignKeyConstraint, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._types import created_at, updated_at, uuid_pk


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)  # software | addon | service | goods
    sales_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", passive_deletes=True)


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="CASCADE"))
    attribute: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    extra_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")  # added in 009

    product: Mapped[Product] = relationship(back_populates="variants")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # list price for display only (API.md rule 7)
    billing_period: Mapped[str] = mapped_column(Text)  # daily | weekly | monthly | yearly
    min_quantity: Mapped[int] = mapped_column(Integer, server_default="1")
    available_from: Mapped[date] = mapped_column(Date)
    available_to: Mapped[date | None] = mapped_column(Date)
    auto_close: Mapped[bool] = mapped_column(Boolean, server_default="false")
    allow_early_close: Mapped[bool] = mapped_column(Boolean, server_default="false")
    allow_pause: Mapped[bool] = mapped_column(Boolean, server_default="false")
    allow_renew: Mapped[bool] = mapped_column(Boolean, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class Tax(Base):
    __tablename__ = "taxes"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    computation: Mapped[str] = mapped_column(Text)  # percentage | fixed
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    product_types: Mapped[list["TaxProductType"]] = relationship(passive_deletes=True)


class TaxProductType(Base):
    """No rows for a tax = it applies to every product type."""

    __tablename__ = "tax_product_types"

    tax_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("taxes.id", ondelete="CASCADE"), primary_key=True)
    product_type: Mapped[str] = mapped_column(Text, primary_key=True)


class QuotationTemplate(Base):
    __tablename__ = "quotation_templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("plans.id", ondelete="RESTRICT"))
    validity_days: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    plan: Mapped[Plan] = relationship()
    lines: Mapped[list["QuotationTemplateLine"]] = relationship(
        back_populates="template", passive_deletes=True, order_by="QuotationTemplateLine.sort_order"
    )


class QuotationTemplateLine(Base):
    __tablename__ = "quotation_template_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["variant_id", "product_id"], ["product_variants.id", "product_variants.product_id"], ondelete="RESTRICT"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("quotation_templates.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    quantity: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    template: Mapped[QuotationTemplate] = relationship(back_populates="lines")
