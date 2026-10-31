import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.models.identity import User
from app.schemas.billing import (
    AutoCloseRequest,
    AutoCloseResult,
    BillingRunDetail,
    BillingRunList,
    BillingRunRequest,
    BillingRunResult,
    DueSubscriptionList,
)
from app.services import auto_close_service
from app.services import billing_service as svc

router = APIRouter(prefix="/billing", tags=["Billing"])

StaffUser = Annotated[User, Depends(require_roles("admin", "staff"))]
AdminUser = Annotated[User, Depends(require_roles("admin"))]


@router.get("/due", response_model=DueSubscriptionList)
def list_due(db: DbSession, _: StaffUser, params: Pagination, as_of: Annotated[date | None, Query(alias="asOf")] = None):
    items, meta = svc.list_due(db, as_of, params)
    return page_of(items, meta)


@router.post("/run", response_model=BillingRunResult)
def run_billing(db: DbSession, user: StaffUser, body: BillingRunRequest | None = None):
    return svc.run_billing(db, body, user)


@router.post("/auto-close", response_model=AutoCloseResult)
def auto_close(db: DbSession, _: AdminUser, body: AutoCloseRequest | None = None):
    """The daily job: close active subscriptions past expiryDate on autoClose plans."""
    return auto_close_service.auto_close_expired(db, body.as_of if body else None)


@router.get("/runs", response_model=BillingRunList)
def list_runs(db: DbSession, _: StaffUser, params: Pagination):
    items, meta = svc.list_runs(db, params)
    return page_of(items, meta)


@router.get("/runs/{id}", response_model=BillingRunDetail)
def get_run(id: uuid.UUID, db: DbSession, _: StaffUser):
    return svc.get_run(db, id)
