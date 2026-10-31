import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.auth import UserOut
from app.schemas.users import StaffCreate, UserList, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_roles("admin"))])


@router.get("", response_model=UserList)
def list_users(
    db: DbSession,
    params: Pagination,
    q: str | None = None,
    role: Annotated[str | None, Query(pattern="^(admin|staff|customer)$")] = None,
    is_active: Annotated[bool | None, Query(alias="isActive")] = None,
):
    rows, meta = user_service.list_users(db, params, q, role, is_active)
    return page_of(rows, meta)


@router.post("/staff", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff(body: StaffCreate, db: DbSession):
    return user_service.create_staff(db, body)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: DbSession):
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, db: DbSession, actor: CurrentUser):
    return user_service.update_user(db, actor, user_id, body)
