"""Authentication and own-profile business logic (contract: Auth tag, API.md rule 1)."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import security
from app.core.errors import AppError
from app.models.identity import Customer, PasswordResetToken, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdate,
    ResetPasswordRequest,
    SignupRequest,
)

logger = logging.getLogger("app.auth")

INVALID_LOGIN = "Invalid email or password"
INVALID_RESET_TOKEN = "Reset token is invalid, already used or expired"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))  # citext: case-insensitive match


# ------------------------------------------------------------------ signup
def signup(db: Session, data: SignupRequest) -> User:
    """Create a customer login. If staff already created a customer with this email and it has no
    login yet, link to that record (keeping its subscriptions) instead of creating a duplicate."""
    if _user_by_email(db, data.email) is not None:
        raise AppError.conflict("An account with this email already exists")

    customer = db.scalar(select(Customer).where(Customer.email == data.email))
    if customer is not None:
        if db.scalar(select(User.id).where(User.customer_id == customer.id)) is not None:
            raise AppError.conflict("An account with this email already exists")
        # Keep what staff entered; only fill gaps from the signup form.
        customer.phone = customer.phone or data.phone
        customer.company = customer.company or data.company
    else:
        customer = Customer(name=data.name, email=data.email, phone=data.phone, company=data.company)
        db.add(customer)
        db.flush()

    user = User(
        name=data.name,
        email=data.email,
        password_hash=security.hash_password(data.password),
        role="customer",
        customer_id=customer.id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent signup for the same email
        db.rollback()
        raise AppError.conflict("An account with this email already exists") from None
    db.refresh(user)
    return user


# ------------------------------------------------------------------- login
def login(db: Session, data: LoginRequest) -> User:
    user = _user_by_email(db, data.email)
    if user is None:
        security.burn_password_check(data.password)
        raise AppError.unauthenticated(INVALID_LOGIN)
    if not security.verify_password(data.password, user.password_hash):
        raise AppError.unauthenticated(INVALID_LOGIN)
    if not user.is_active:  # only reached with the right password, so this does not leak account status
        raise AppError.forbidden("This account is deactivated")
    user.last_login_at = _now()
    db.commit()
    db.refresh(user)
    return user


# --------------------------------------------------------- password reset
def forgot_password(db: Session, email: str) -> str | None:
    """Always succeeds from the caller's view. Returns the raw token only so tests can use it;
    routers must discard it. Until email sending exists, the link is logged to the console."""
    user = _user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    settings = get_settings()
    raw, token_hash = security.new_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=_now() + timedelta(minutes=settings.reset_token_minutes),
        )
    )
    db.commit()
    logger.info("Password reset link for %s: %s/reset-password?token=%s", user.email, settings.frontend_url, raw)
    return raw


def reset_password(db: Session, data: ResetPasswordRequest) -> None:
    row = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == security.hash_reset_token(data.token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > _now(),
        )
        .with_for_update()  # two concurrent uses of one token: the second sees used_at set
    )
    user = db.get(User, row.user_id) if row else None
    if row is None or user is None or not user.is_active:
        raise AppError.validation(INVALID_RESET_TOKEN, field="token")

    user.password_hash = security.hash_password(data.new_password)
    now = _now()
    # Single use, and retire any other open links for this user.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.commit()


def change_password(db: Session, user: User, data: ChangePasswordRequest) -> None:
    if not security.verify_password(data.current_password, user.password_hash):
        raise AppError.validation("Current password is incorrect", field="currentPassword")
    user.password_hash = security.hash_password(data.new_password)
    db.commit()


# -------------------------------------------------------------------- me
_ADDRESS_COLUMNS = {
    "line1": "address_line1",
    "line2": "address_line2",
    "city": "city",
    "state": "state",
    "postal_code": "postal_code",
    "country": "country",
}


def update_me(db: Session, user: User, data: ProfileUpdate) -> User:
    """Partial update of the caller. name applies to the user (and mirrors to the customer record);
    phone, company and address only exist on customers and are ignored for admin/staff."""
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        user.name = changes["name"]

    customer = db.get(Customer, user.customer_id) if user.customer_id else None
    if customer is not None:
        if changes.get("name") is not None:
            customer.name = changes["name"]
        for field in ("phone", "company"):
            if field in changes:
                setattr(customer, field, changes[field])
        for key, value in (changes.get("address") or {}).items():
            setattr(customer, _ADDRESS_COLUMNS[key], value)

    db.commit()
    db.refresh(user)
    return user
