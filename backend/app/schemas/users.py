from app.schemas.auth import UserName, UserOut
from app.schemas.common import CamelModel, Email, NewPassword, PageMeta


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
