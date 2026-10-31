import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.plans import BillingPeriod, PlanInput, PlanList, PlanOut, PlanUpdate
from app.services import plans as plan_service

router = APIRouter(prefix="/plans", tags=["Plans"])

AdminOnly = Depends(require_roles("admin"))


@router.get("", response_model=PlanList)
def list_plans(
    db: DbSession,
    user: CurrentUser,
    params: Pagination,
    q: str | None = None,
    billing_period: Annotated[BillingPeriod | None, Query(alias="billingPeriod")] = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
):
    rows, meta = plan_service.list_plans(db, user, params, q, billing_period, is_active)
    return page_of(rows, meta)


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
def create_plan(body: PlanInput, db: DbSession):
    return plan_service.create_plan(db, body)


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return plan_service.get_plan(db, user, plan_id)


@router.patch("/{plan_id}", response_model=PlanOut, dependencies=[AdminOnly])
def update_plan(plan_id: uuid.UUID, body: PlanUpdate, db: DbSession):
    return plan_service.update_plan(db, plan_id, body)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def deactivate_plan(plan_id: uuid.UUID, db: DbSession):
    plan_service.deactivate_plan(db, plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
