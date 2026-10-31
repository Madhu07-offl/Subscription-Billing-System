import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession, require_roles
from app.schemas.reports import DashboardSummary, GroupBy, RevenueSeries
from app.services import reports as report_service

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(require_roles("admin", "staff"))])

From = Annotated[date | None, Query(alias="from", description="Start date (inclusive). Defaults to the 1st of this month.")]
To = Annotated[date | None, Query(description="End date (inclusive). Defaults to today.")]
PlanId = Annotated[uuid.UUID | None, Query(alias="planId")]
CustomerId = Annotated[uuid.UUID | None, Query(alias="customerId")]


@router.get("/summary", response_model=DashboardSummary)
def get_summary(db: DbSession, from_: From = None, to: To = None, plan_id: PlanId = None, customer_id: CustomerId = None):
    return report_service.summary(db, from_, to, plan_id, customer_id)


@router.get("/revenue", response_model=RevenueSeries)
def get_revenue(
    db: DbSession,
    from_: From = None,
    to: To = None,
    group_by: Annotated[GroupBy, Query(alias="groupBy")] = "month",
    plan_id: PlanId = None,
    customer_id: CustomerId = None,
):
    return {"data": report_service.revenue(db, from_, to, group_by, plan_id, customer_id)}
