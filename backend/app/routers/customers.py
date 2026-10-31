import uuid

from fastapi import APIRouter, Depends, status

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.customers import CustomerInput, CustomerList, CustomerOut, CustomerUpdate
from app.services import customers as customer_service

router = APIRouter(prefix="/customers", tags=["Customers"], dependencies=[Depends(require_roles("admin", "staff"))])


@router.get("", response_model=CustomerList)
def list_customers(db: DbSession, params: Pagination, q: str | None = None):
    rows, meta = customer_service.list_customers(db, params, q)
    return page_of(rows, meta)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(body: CustomerInput, db: DbSession):
    return customer_service.create_customer(db, body)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: uuid.UUID, db: DbSession):
    return customer_service.get_customer(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: uuid.UUID, body: CustomerUpdate, db: DbSession):
    return customer_service.update_customer(db, customer_id, body)
