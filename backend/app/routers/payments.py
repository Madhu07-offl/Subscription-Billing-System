import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.models.identity import User
from app.schemas.invoices import PaymentInput, PaymentList, PaymentMethod, PaymentOut
from app.services import payment_service as svc

router = APIRouter(prefix="/payments", tags=["Payments"])

StaffUser = Annotated[User, Depends(require_roles("admin", "staff"))]
AdminUser = Annotated[User, Depends(require_roles("admin"))]


@router.get("", response_model=PaymentList)
def list_payments(
    db: DbSession,
    user: CurrentUser,
    params: Pagination,
    invoice_id: Annotated[uuid.UUID | None, Query(alias="invoiceId")] = None,
    customer_id: Annotated[uuid.UUID | None, Query(alias="customerId")] = None,
    method: PaymentMethod | None = None,
    paid_from: Annotated[date | None, Query(alias="paidFrom")] = None,
    paid_to: Annotated[date | None, Query(alias="paidTo")] = None,
):
    items, meta = svc.list_payments(
        db, user, params, invoice_id=invoice_id, customer_id=customer_id, method=method,
        paid_from=paid_from, paid_to=paid_to,
    )
    return page_of(items, meta)


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(body: PaymentInput, db: DbSession, user: StaffUser):
    return svc.record_payment(db, body, user)


@router.get("/{id}", response_model=PaymentOut)
def get_payment(id: uuid.UUID, db: DbSession, user: CurrentUser):
    return svc.get_payment(db, id, user)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def void_payment(id: uuid.UUID, db: DbSession, user: AdminUser):
    svc.void_payment(db, id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
