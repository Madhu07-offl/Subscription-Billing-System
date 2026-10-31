import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.taxes import TaxInput, TaxList, TaxOut, TaxUpdate
from app.services import taxes as tax_service

router = APIRouter(prefix="/taxes", tags=["Taxes"])

AdminOnly = Depends(require_roles("admin"))
AdminOrStaff = Depends(require_roles("admin", "staff"))


@router.get("", response_model=TaxList, dependencies=[AdminOrStaff])
def list_taxes(db: DbSession, params: Pagination, is_active: Annotated[bool | None, Query(alias="isActive")] = None):
    rows, meta = tax_service.list_taxes(db, params, is_active)
    return page_of(rows, meta)


@router.post("", response_model=TaxOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
def create_tax(body: TaxInput, db: DbSession):
    return tax_service.create_tax(db, body)


@router.get("/{tax_id}", response_model=TaxOut, dependencies=[AdminOrStaff])
def get_tax(tax_id: uuid.UUID, db: DbSession):
    return tax_service.get_tax(db, tax_id)


@router.patch("/{tax_id}", response_model=TaxOut, dependencies=[AdminOnly])
def update_tax(tax_id: uuid.UUID, body: TaxUpdate, db: DbSession):
    return tax_service.update_tax(db, tax_id, body)


@router.delete("/{tax_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def deactivate_tax(tax_id: uuid.UUID, db: DbSession):
    tax_service.deactivate_tax(db, tax_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
