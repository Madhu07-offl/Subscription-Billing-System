from typing import Annotated

from pydantic import StringConstraints

from app.schemas.auth import UserOut
from app.schemas.common import CamelModel, Email, NewPassword, PageMeta

# Stripped before the length check, so a blank name is a 400 instead of failing the database CHECK.
UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StaffCreate(CamelModel):
    name: UserName
    email: Email
    password: NewPassword


class UserUpdate(CamelModel):
    """Partial update: only fields present in the body are applied."""

    name: UserName | None = None
    is_active: bool | None = None


class UserList(CamelModel):
    data: list[UserOut]
    meta: PageMeta
