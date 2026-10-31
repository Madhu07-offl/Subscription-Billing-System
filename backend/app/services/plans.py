"""Plans (contract: Plans tag). Edits affect future billing only; issued invoices keep their own data."""
import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Plan
from app.models.identity import User
from app.schemas.plans import PlanInput, PlanUpdate

NOT_NULL_FIELDS = {
    "name", "price", "billing_period", "min_quantity", "available_from",
    "auto_close", "allow_early_close", "allow_pause", "allow_renew", "is_active",
}  # fmt: skip
BAD_DATES = "availableTo cannot be before availableFrom"


def _visible_to_customers(today: date):
    return (
        Plan.is_active.is_(True),
        Plan.available_from <= today,
        or_(Plan.available_to.is_(None), Plan.available_to >= today),
    )


def _get(db: Session, plan_id: uuid.UUID, viewer: User | None = None) -> Plan:
    stmt = select(Plan).where(Plan.id == plan_id)
    if viewer is not None and viewer.role == "customer":
        stmt = stmt.where(*_visible_to_customers(date.today()))
    plan = db.scalar(stmt)
    if plan is None:
        raise AppError.not_found("Plan not found")
    return plan


def list_plans(
    db: Session, viewer: User, params: PageParams, q: str | None, billing_period: str | None, is_active: bool | None
):
    stmt = select(Plan)
    if q:
        stmt = stmt.where(Plan.name.ilike(f"%{q.strip()}%"))
    if billing_period:
        stmt = stmt.where(Plan.billing_period == billing_period)
    if viewer.role == "customer":
        stmt = stmt.where(*_visible_to_customers(date.today()))
    elif is_active is not None:
        stmt = stmt.where(Plan.is_active == is_active)
    return paginate(db, stmt.order_by(Plan.created_at.desc(), Plan.id), params)


def get_plan(db: Session, viewer: User, plan_id: uuid.UUID) -> Plan:
    return _get(db, plan_id, viewer)


def _check_dates(available_from: date, available_to: date | None) -> None:
    if available_to is not None and available_to < available_from:
        raise AppError.business_rule(BAD_DATES)


def create_plan(db: Session, data: PlanInput) -> Plan:
    _check_dates(data.available_from, data.available_to)
    plan = Plan(**data.model_dump())
    plan.name = plan.name.strip()
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(db: Session, plan_id: uuid.UUID, data: PlanUpdate) -> Plan:
    plan = _get(db, plan_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field in NOT_NULL_FIELDS:
            raise AppError.validation(f"{field} cannot be null", field=field)
    _check_dates(changes.get("available_from", plan.available_from), changes.get("available_to", plan.available_to))
    for field, value in changes.items():
        setattr(plan, field, value.strip() if field == "name" else value)
    db.commit()
    db.refresh(plan)
    return plan


def deactivate_plan(db: Session, plan_id: uuid.UUID) -> None:
    plan = _get(db, plan_id)
    plan.is_active = False
    db.commit()
