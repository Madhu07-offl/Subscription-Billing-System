import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, PageMeta

TemplateName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ValidityDays = Annotated[int, Field(ge=1, le=3650)]
Quantity = Annotated[int, Field(ge=1, le=1_000_000)]


class TemplateLine(CamelModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: Quantity


class TemplateInput(CamelModel):
    name: TemplateName
    plan_id: uuid.UUID
    validity_days: ValidityDays
    lines: list[TemplateLine]
    notes: str | None = Field(default=None, max_length=2000)


class TemplateUpdate(CamelModel):
    """Partial update: only fields present in the body are applied. `lines`, when sent, replaces all lines."""

    name: TemplateName | None = None
    plan_id: uuid.UUID | None = None
    validity_days: ValidityDays | None = None
    lines: list[TemplateLine] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TemplateOut(CamelModel):
    id: uuid.UUID
    name: str
    plan_id: uuid.UUID
    plan_name: str
    validity_days: int
    lines: list[TemplateLine]
    notes: str | None
    created_at: datetime


class TemplateList(CamelModel):
    data: list[TemplateOut]
    meta: PageMeta
