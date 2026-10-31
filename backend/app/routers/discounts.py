import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.discounts import DiscountInput, DiscountList, DiscountOut, DiscountUpdate
from app.services import discounts as discount_service

router = APIRouter(prefix="/discounts", tags=["Discounts"])

AdminOnly = Depends(require_roles("admin"))
AdminOrStaff = Depends(require_roles("admin", "staff"))


@router.get("", response_model=DiscountList, dependencies=[AdminOrStaff])
def list_discounts(
    db: DbSession,
    params: Pagination,
    q: str | None = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
    valid_on: Annotated[date | None, Query(alias="validOn")] = None,
):
    rows, meta = discount_service.list_discounts(db, params, q, is_active, valid_on)
    return page_of(rows, meta)


@router.post("", response_model=DiscountOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
def create_discount(body: DiscountInput, db: DbSession):
    return discount_service.create_discount(db, body)


@router.get("/{discount_id}", response_model=DiscountOut, dependencies=[AdminOrStaff])
def get_discount(discount_id: uuid.UUID, db: DbSession):
    return discount_service.get_discount(db, discount_id)


@router.patch("/{discount_id}", response_model=DiscountOut, dependencies=[AdminOnly])
def update_discount(discount_id: uuid.UUID, body: DiscountUpdate, db: DbSession):
    return discount_service.update_discount(db, discount_id, body)


@router.delete("/{discount_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def deactivate_discount(discount_id: uuid.UUID, db: DbSession):
    discount_service.deactivate_discount(db, discount_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
