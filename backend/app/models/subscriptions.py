import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._types import NOW, created_at, updated_at, uuid_pk


class DocumentSequence(Base):
    """Counters behind SUB-0001 / INV-2026-0001. Use next_document_number(key); never edit directly."""

    __tablename__ = "document_sequences"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    prefix: Mapped[str] = mapped_column(Text)
    include_year: Mapped[bool] = mapped_column(Boolean, server_default="false")
    padding: Mapped[int] = mapped_column(Integer, server_default="4")
    current_year: Mapped[int | None] = mapped_column(Integer)
    last_value: Mapped[int] = mapped_column(BigInteger, server_default="0")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    # READ-ONLY: DB default next_document_number('subscription'); fetched back after INSERT.
    number: Mapped[str] = mapped_column(Text, unique=True, server_default=text("next_document_number('subscription')"))
    status: Mapped[str] = mapped_column(Text, server_default="draft")  # draft|quotation|confirmed|active|closed
    is_paused: Mapped[bool] = mapped_column(Boolean, server_default="false")
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"))
    # plan_id / start_date / expiry_date are nullable for drafts only (010: subscriptions_complete_ck)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("plans.id", ondelete="RESTRICT"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("quotation_templates.id", ondelete="SET NULL")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    # nullable, no default: required once the subscription leaves draft (010: subscriptions_complete_ck)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    quotation_valid_until: Mapped[date | None] = mapped_column(Date)
    next_billing_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    customer = relationship("Customer")
    plan = relationship("Plan")
    lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription", passive_deletes=True, order_by="SubscriptionLine.sort_order"
    )


class SubscriptionLine(Base):
    __tablename__ = "subscription_lines"
    __table_args__ = (
        # Variant must belong to the product; deleting a variant nulls only variant_id (PG15+ column list).
        ForeignKeyConstraint(
            ["variant_id", "product_id"],
            ["product_variants.id", "product_variants.product_id"],
            ondelete="SET NULL (variant_id)",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Snapshots, so a locked subscription is unaffected by later catalogue edits.
    product_name: Mapped[str] = mapped_column(Text)
    variant_label: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("taxes.id", ondelete="SET NULL"))
    tax_name: Mapped[str | None] = mapped_column(Text)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    # Generated: round(quantity * unit_price, 2). Read-only. (Postgres reports generated columns as nullable.)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(quantity * unit_price, 2)", persisted=True), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    subscription: Mapped[Subscription] = relationship(back_populates="lines")


class SubscriptionStatusHistory(Base):
    __tablename__ = "subscription_status_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(Text, server_default="status_change")  # created|status_change|paused|resumed|renewed
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
