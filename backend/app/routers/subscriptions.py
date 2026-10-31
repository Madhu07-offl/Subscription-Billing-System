import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.models.identity import User
from app.schemas.invoices import InvoiceList
from app.schemas.subscriptions import (
    CloseRequest,
    RenewRequest,
    StatusChangeList,
    SubscriptionInput,
    SubscriptionList,
    SubscriptionOut,
    SubscriptionRequest,
    SubscriptionStatus,
    SubscriptionUpdate,
)
from app.services import invoice_service
from app.services import subscription_service as svc

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

StaffUser = Annotated[User, Depends(require_roles("admin", "staff"))]
CustomerUser = Annotated[User, Depends(require_roles("customer"))]


@router.get("", response_model=SubscriptionList)
def list_subscriptions(
    db: DbSession,
    user: CurrentUser,
    params: Pagination,
    q: str | None = None,
    status: SubscriptionStatus | None = None,
    customer_id: Annotated[uuid.UUID | None, Query(alias="customerId")] = None,
    plan_id: Annotated[uuid.UUID | None, Query(alias="planId")] = None,
    expiring_before: Annotated[date | None, Query(alias="expiringBefore")] = None,
):
    items, meta = svc.list_subscriptions(
        db, user, params, q=q, status=status, customer_id=customer_id, plan_id=plan_id,
        expiring_before=expiring_before,
    )
    return page_of(items, meta)


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(body: SubscriptionInput, db: DbSession, user: StaffUser):
    return svc.create_subscription(db, body, user)


# Declared before /{id} so "request" is never parsed as an id.
@router.post("/request", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def request_subscription(body: SubscriptionRequest, db: DbSession, user: CustomerUser):
    return svc.request_subscription(db, body, user)


@router.get("/{id}", response_model=SubscriptionOut)
def get_subscription(id: uuid.UUID, db: DbSession, user: CurrentUser):
    return svc.get_subscription(db, id, user)


@router.patch("/{id}", response_model=SubscriptionOut)
def update_subscription(id: uuid.UUID, body: SubscriptionUpdate, db: DbSession, user: StaffUser):
    return svc.update_subscription(db, id, body, user)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(id: uuid.UUID, db: DbSession, user: StaffUser):
    svc.delete_subscription(db, id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{id}/history", response_model=StatusChangeList)
def subscription_history(id: uuid.UUID, db: DbSession, user: CurrentUser, params: Pagination):
    items, meta = svc.list_history(db, id, user, params)
    return page_of(items, meta)


@router.post("/{id}/send-quotation", response_model=SubscriptionOut)
def send_quotation(id: uuid.UUID, db: DbSession, user: StaffUser):
    return svc.send_quotation(db, id, user)


@router.post("/{id}/confirm", response_model=SubscriptionOut)
def confirm(id: uuid.UUID, db: DbSession, user: StaffUser):
    return svc.confirm(db, id, user)


@router.post("/{id}/activate", response_model=SubscriptionOut)
def activate(id: uuid.UUID, db: DbSession, user: StaffUser):
    return svc.activate(db, id, user)


@router.post("/{id}/close", response_model=SubscriptionOut)
def close(id: uuid.UUID, db: DbSession, user: CurrentUser, body: CloseRequest | None = None):
    return svc.close(db, id, body, user)


@router.post("/{id}/pause", response_model=SubscriptionOut)
def pause(id: uuid.UUID, db: DbSession, user: CurrentUser):
    return svc.pause(db, id, user)


@router.post("/{id}/resume", response_model=SubscriptionOut)
def resume(id: uuid.UUID, db: DbSession, user: CurrentUser):
    return svc.resume(db, id, user)


@router.post("/{id}/renew", response_model=SubscriptionOut)
def renew(id: uuid.UUID, db: DbSession, user: CurrentUser, body: RenewRequest | None = None):
    return svc.renew(db, id, body, user)


@router.get("/{id}/invoices", response_model=InvoiceList)
def subscription_invoices(id: uuid.UUID, db: DbSession, user: CurrentUser, params: Pagination):
    items, meta = invoice_service.list_for_subscription(db, id, user, params)
    return page_of(items, meta)
