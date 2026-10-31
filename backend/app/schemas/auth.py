import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import Address, CamelModel, Email, NewPassword

# Stripped before the length check, so a blank name is a 400 instead of failing the database CHECK.
UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SignupRequest(CamelModel):
    name: UserName
    email: Email
    password: NewPassword
    company: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)


class LoginRequest(CamelModel):
    # Plain str on purpose: never reveal password rules (or reject old passwords) at login.
    email: Email
    password: str = Field(min_length=1, max_length=1024)


class ForgotPasswordRequest(CamelModel):
    email: Email


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: NewPassword


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: NewPassword


class ProfileUpdate(CamelModel):
    """Partial update. phone/company/address live on the customer record, so they only apply to customers."""

    name: UserName | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=200)
    address: Address | None = None


class UserOut(CamelModel):
    id: uuid.UUID
    name: str
    email: str
    role: Literal["admin", "staff", "customer"]
    is_active: bool
    customer_id: uuid.UUID | None
    created_at: datetime


class AuthResponse(CamelModel):
    token: str
    expires_in: int
    user: UserOut
