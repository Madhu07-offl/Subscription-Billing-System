import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Computed, Date, DateTime, ForeignKey, Integer, Numeric, Text, Uuid, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._types import NOW, created_at, updated_at, uuid_pk


class BillingRun(Base):
    __tablename__ = "billing_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    as_of: Mapped[date] = mapped_column(Date)
    dry_run: Mapped[bool] = mapped_column(Boolean, server_default="false")
    due_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_count: Mapped[int] = mapped_column(Integer, server_default="0")
    already_billed: Mapped[int] = mapped_column(Integer, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, server_default="0")
    failures: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = uuid_pk()
    # READ-ONLY: DB default next_document_number('invoice').
    number: Mapped[str] = mapped_column(Text, unique=True, server_default=text("next_document_number('invoice')"))
    status: Mapped[str] = mapped_column(Text, server_default="draft")  # draft|confirmed|paid|cancelled
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="RESTRICT"))
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="RESTRICT"))
    billing_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("billing_runs.id", ondelete="SET NULL"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    # READ-ONLY: maintained by trg_payments_sync_invoice together with the confirmed <-> paid status.
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
    # READ-ONLY snapshot of the customer (009). NOT NULL in the DB; trg_invoices_billing_snapshot fills
    # them on INSERT when they are NULL, so code leaves them unset (an explicit value would bypass it).
    billing_name: Mapped[str] = mapped_column(Text)
    billing_email: Mapped[str] = mapped_column(CITEXT)
    billing_company: Mapped[str | None] = mapped_column(Text)
    billing_address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    subscription = relationship("Subscription")
    customer = relationship("Customer")
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", passive_deletes=True, order_by="InvoiceLine.sort_order"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("products.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("discounts.id", ondelete="RESTRICT"))
    discount_name: Mapped[str | None] = mapped_column(Text)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    tax_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("taxes.id", ondelete="RESTRICT"))
    tax_name: Mapped[str | None] = mapped_column(Text)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")
    # Generated: round(quantity * unit_price - discount_amount, 2). Read-only.
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), Computed("round(quantity * unit_price - discount_amount, 2)", persisted=True), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("invoices.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(Text)  # cash|bank_transfer|card|upi|cheque|other
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    # Void a payment by setting voided_at (and voided_by). is_voided is generated from it: read-only.
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_voided: Mapped[bool] = mapped_column(Boolean, Computed("voided_at is not null", persisted=True), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
