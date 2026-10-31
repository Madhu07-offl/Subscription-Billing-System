import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._types import NOW, created_at, updated_at, uuid_pk


class Discount(Base):
    __tablename__ = "discounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)  # percentage | fixed
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    scope: Mapped[str] = mapped_column(Text)  # products | subscriptions
    min_purchase_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    min_quantity: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    # READ-ONLY: maintained by trigger from discount_usages. Never assign in code.
    used_count: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    products: Mapped[list["DiscountProduct"]] = relationship(passive_deletes=True)
    subscriptions: Mapped[list["DiscountSubscription"]] = relationship(passive_deletes=True)


class DiscountProduct(Base):
    __tablename__ = "discount_products"

    discount_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("discounts.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)


class DiscountSubscription(Base):
    """No rows for a scope=subscriptions discount = applies to all subscriptions."""

    __tablename__ = "discount_subscriptions"

    discount_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("discounts.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True
    )


class DiscountUsage(Base):
    """Insert = used_count + 1, set released_at = used_count - 1 (trigger). Unique (discount_id, invoice_id)."""

    __tablename__ = "discount_usages"

    id: Mapped[uuid.UUID] = uuid_pk()
    discount_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("discounts.id", ondelete="RESTRICT"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id", ondelete="CASCADE"))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
