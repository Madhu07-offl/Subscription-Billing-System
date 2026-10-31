from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, StringConstraints
from pydantic.alias_generators import to_camel

from app.core.security import password_problems


class CamelModel(BaseModel):
    """Base for every request/response model: camelCase on the wire, snake_case in Python."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# Money is a string with exactly two decimals on the wire ("560.00"), Decimal in Python.
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")]

# Deliberately not pydantic EmailStr: email-validator rejects reserved TLDs such as the seeded
# admin@brightloop.test. Format check only; the DB stores it lowercase in a citext column.
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]


def _check_password(value: str) -> str:
    problems = password_problems(value)
    if problems:
        raise ValueError("; ".join(problems))
    return value


# New passwords only. Login/current-password fields stay plain str so old accounts can still log in.
NewPassword = Annotated[str, AfterValidator(_check_password)]


class Message(CamelModel):
    message: str


class PageMeta(CamelModel):
    page: int
    limit: int
    total: int
    total_pages: int


class Address(CamelModel):
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
