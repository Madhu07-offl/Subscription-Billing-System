import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.models.identity import User
from app.schemas.invoices import InvoiceList, InvoiceOut, InvoiceStatus, InvoiceUpdate, SendInvoiceRequest
from app.services import invoice_service as svc

router = APIRouter(prefix="/invoices", tags=["Invoices"])

StaffUser = Annotated[User, Depends(require_roles("admin", "staff"))]


@router.get("", response_model=InvoiceList)
def list_invoices(
    db: DbSession,
    user: CurrentUser,
    params: Pagination,
    q: str | None = None,
    status: InvoiceStatus | None = None,
    customer_id: Annotated[uuid.UUID | None, Query(alias="customerId")] = None,
    subscription_id: Annotated[uuid.UUID | None, Query(alias="subscriptionId")] = None,
    is_overdue: Annotated[bool | None, Query(alias="isOverdue")] = None,
    has_balance: Annotated[bool | None, Query(alias="hasBalance")] = None,
    issued_from: Annotated[date | None, Query(alias="issuedFrom")] = None,
    issued_to: Annotated[date | None, Query(alias="issuedTo")] = None,
):
    items, meta = svc.list_invoices(
        db, user, params, q=q, status=status, customer_id=customer_id, subscription_id=subscription_id,
        is_overdue=is_overdue, has_balance=has_balance, issued_from=issued_from, issued_to=issued_to,
    )
    return page_of(items, meta)


@router.get("/{id}", response_model=InvoiceOut)
def get_invoice(id: uuid.UUID, db: DbSession, user: CurrentUser):
    return svc.get_invoice(db, id, user)


@router.patch("/{id}", response_model=InvoiceOut)
def update_invoice(id: uuid.UUID, body: InvoiceUpdate, db: DbSession, user: StaffUser):
    return svc.update_invoice(db, id, body, user)


@router.post("/{id}/confirm", response_model=InvoiceOut)
def confirm_invoice(id: uuid.UUID, db: DbSession, user: StaffUser):
    return svc.confirm(db, id, user)


@router.post("/{id}/cancel", response_model=InvoiceOut)
def cancel_invoice(id: uuid.UUID, db: DbSession, user: StaffUser):
    return svc.cancel(db, id, user)


@router.post("/{id}/send", response_model=InvoiceOut)
def send_invoice(id: uuid.UUID, db: DbSession, user: StaffUser, body: SendInvoiceRequest | None = None):
    return svc.send(db, id, body, user)
