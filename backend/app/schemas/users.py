from pydantic import Field

from app.schemas.auth import UserOut
from app.schemas.common import CamelModel, Email, NewPassword, PageMeta


class StaffCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    email: Email
    password: NewPassword


class UserUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class UserList(CamelModel):
    data: list[UserOut]
    meta: PageMeta
