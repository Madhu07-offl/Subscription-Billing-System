import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import Address, CamelModel, Email, PageMeta

# Stripped before the length check, so a blank name is a 400 instead of failing the database CHECK.
CustomerName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CustomerInput(CamelModel):
    name: CustomerName
    email: Email
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=100)
    address: Address | None = None


class CustomerUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    name: CustomerName | None = None
    email: Email | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=100)
    address: Address | None = None


class CustomerOut(CamelModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    company: str | None
    tax_id: str | None
    address: Address
    has_login: bool
    active_subscriptions: int
    created_at: datetime


class CustomerList(CamelModel):
    data: list[CustomerOut]
    meta: PageMeta
