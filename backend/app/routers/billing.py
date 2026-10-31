import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.models.identity import User
from app.schemas.billing import (
    BillingRunDetail,
    BillingRunList,
    BillingRunRequest,
    BillingRunResult,
    DueSubscriptionList,
)
from app.services import billing_service as svc

router = APIRouter(prefix="/billing", tags=["Billing"])

StaffUser = Annotated[User, Depends(require_roles("admin", "staff"))]


@router.get("/due", response_model=DueSubscriptionList)
def list_due(db: DbSession, _: StaffUser, params: Pagination, as_of: Annotated[date | None, Query(alias="asOf")] = None):
    items, meta = svc.list_due(db, as_of, params)
    return page_of(items, meta)


@router.post("/run", response_model=BillingRunResult)
def run_billing(db: DbSession, user: StaffUser, body: BillingRunRequest | None = None):
    return svc.run_billing(db, body, user)


@router.get("/runs", response_model=BillingRunList)
def list_runs(db: DbSession, _: StaffUser, params: Pagination):
    items, meta = svc.list_runs(db, params)
    return page_of(items, meta)


@router.get("/runs/{id}", response_model=BillingRunDetail)
def get_run(id: uuid.UUID, db: DbSession, _: StaffUser):
    return svc.get_run(db, id)
