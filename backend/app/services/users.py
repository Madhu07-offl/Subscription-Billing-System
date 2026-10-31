"""User management (contract: Users tag). Admin only; the router enforces the role."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.identity import Customer, User
from app.schemas.users import StaffCreate, UserUpdate


def list_users(db: Session, params: PageParams, q: str | None, role: str | None, is_active: bool | None):
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.email.ilike(like)))
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    return paginate(db, stmt.order_by(User.created_at.desc(), User.id), params)


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError.not_found("User not found")
    return user


def create_staff(db: Session, data: StaffCreate) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise AppError.conflict("An account with this email already exists")
    user = User(name=data.name, email=data.email, password_hash=security.hash_password(data.password), role="staff")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict("An account with this email already exists") from None
    db.refresh(user)
    return user


def update_user(db: Session, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = get_user(db, user_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and user.id == actor.id:
        raise AppError.business_rule("You cannot deactivate your own account")
    if changes.get("name") is not None:
        user.name = changes["name"]
        if user.customer_id:  # keep the customer record's display name in step, as PATCH /auth/me does
            customer = db.get(Customer, user.customer_id)
            if customer is not None:
                customer.name = changes["name"]
    if changes.get("is_active") is not None:
        user.is_active = changes["is_active"]
    db.commit()
    db.refresh(user)
    return user
