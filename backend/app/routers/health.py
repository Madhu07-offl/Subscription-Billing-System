from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import DbSession
from app.core.errors import INTERNAL, AppError

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(db: DbSession):
    """Public liveness + database check (SELECT 1)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise AppError(INTERNAL, "Database unavailable") from None
    return {"status": "ok", "database": "up"}
