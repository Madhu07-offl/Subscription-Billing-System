from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db import SessionLocal
from app.models.identity import User

_bearer = HTTPBearer(auto_error=False)  # we raise our own 401 in the contract error shape


def get_db() -> Iterator[Session]:
    """One session per request. Services commit; anything uncommitted is rolled back on close."""
    with SessionLocal() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AppError.unauthenticated()
    user = db.get(User, decode_access_token(credentials.credentials))
    if user is None:
        raise AppError.unauthenticated("Invalid or expired token")
    if not user.is_active:
        raise AppError.forbidden("This account is deactivated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory mirroring `x-roles` in openapi.yaml: Depends(require_roles('admin', 'staff'))."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise AppError.forbidden()
        return user

    return checker
