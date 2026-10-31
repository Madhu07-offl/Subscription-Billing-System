import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Address, CamelModel, Money, PageMeta
from app.schemas.subscriptions import CustomerRef

InvoiceStatus = Literal["draft", "confirmed", "paid", "cancelled"]
PaymentMethod = Literal["cash", "bank_transfer", "card", "upi", "cheque", "other"]


class InvoiceLineOut(CamelModel):
    id: uuid.UUID
    product_id: uuid.UUID
    description: str
    quantity: int
    unit_price: Money
    discount_id: uuid.UUID | None
    discount_amount: Money
    tax_id: uuid.UUID | None
    tax_name: str | None
    tax_rate: float | None
    tax_amount: Money
    amount: Money


class InvoiceSummaryOut(CamelModel):
    id: uuid.UUID
    number: str
    status: InvoiceStatus
    subscription_id: uuid.UUID
    subscription_number: str
    customer: CustomerRef
    period_start: date
    period_end: date
    issue_date: date | None
    due_date: date | None
    subtotal: Money
    discount_total: Money
    tax_total: Money
    total: Money
    amount_paid: Money
    amount_due: Money
    is_overdue: bool
    sent_at: datetime | None
    created_at: datetime


class CustomerDetails(CamelModel):
    """Snapshot of the customer copied onto the invoice (invoices.billing_*)."""

    name: str
    email: str
    phone: str | None = None
    company: str | None = None
    tax_id: str | None = None
    address: Address | None = None


class PaymentOut(CamelModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str
    customer: CustomerRef
    method: PaymentMethod
    amount: Money
    payment_date: date
    reference: str | None
    note: str | None
    is_voided: bool
    recorded_by: uuid.UUID | None
    created_at: datetime


class InvoiceOut(InvoiceSummaryOut):
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]
    customer_details: CustomerDetails
    notes: str | None


class InvoiceList(CamelModel):
    data: list[InvoiceSummaryOut]
    meta: PageMeta


class InvoiceLineUpdate(CamelModel):
    id: uuid.UUID
    description: str | None = Field(default=None, min_length=1)
    quantity: int | None = Field(default=None, ge=1)
    unit_price: Money | None = Field(default=None, ge=0)


class InvoiceUpdate(CamelModel):
    """Partial body: only what is sent changes; `lines` lists only the lines to change."""

    notes: str | None = None
    lines: list[InvoiceLineUpdate] | None = None


class SendInvoiceRequest(CamelModel):
    to: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    message: str | None = None


# ----------------------------------------------------------------------------------------------- payments
class PaymentInput(CamelModel):
    """amount is checked by the service (422 unless 0 < amount <= amountDue), not here (which would be a 400)."""

    invoice_id: uuid.UUID
    method: PaymentMethod
    amount: Money
    payment_date: date
    reference: str | None = None
    note: str | None = None


class PaymentList(CamelModel):
    data: list[PaymentOut]
    meta: PageMeta
