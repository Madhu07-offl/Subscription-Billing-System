import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.products import (
    ProductInput,
    ProductList,
    ProductOut,
    ProductType,
    ProductUpdate,
    VariantInput,
    VariantOut,
    VariantUpdate,
)
from app.services import products as product_service

router = APIRouter(prefix="/products", tags=["Products"])

AdminOnly = Depends(require_roles("admin"))


@router.get("", response_model=ProductList)
def list_products(
    db: DbSession,
    user: CurrentUser,
    params: Pagination,
    q: str | None = None,
    type: ProductType | None = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
):
    rows, meta = product_service.list_products(db, user, params, q, type, is_active)
    return page_of(rows, meta)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
def create_product(body: ProductInput, db: DbSession):
    return product_service.create_product(db, body)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return product_service.get_product(db, user, product_id)


@router.patch("/{product_id}", response_model=ProductOut, dependencies=[AdminOnly])
def update_product(product_id: uuid.UUID, body: ProductUpdate, db: DbSession):
    return product_service.update_product(db, product_id, body)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def archive_product(product_id: uuid.UUID, db: DbSession):
    product_service.archive_product(db, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{product_id}/variants", response_model=VariantOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly]
)
def create_variant(product_id: uuid.UUID, body: VariantInput, db: DbSession):
    return product_service.create_variant(db, product_id, body)


@router.patch("/{product_id}/variants/{variant_id}", response_model=VariantOut, dependencies=[AdminOnly])
def update_variant(product_id: uuid.UUID, variant_id: uuid.UUID, body: VariantUpdate, db: DbSession):
    return product_service.update_variant(db, product_id, variant_id, body)


@router.delete("/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def delete_variant(product_id: uuid.UUID, variant_id: uuid.UUID, db: DbSession):
    product_service.delete_variant(db, product_id, variant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
