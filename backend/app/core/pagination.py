import math
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas.common import PageMeta

T = TypeVar("T")


@dataclass(frozen=True)
class PageParams:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, limit=limit)


Pagination = Annotated[PageParams, Depends(page_params)]


def paginate(db: Session, stmt: Select[Any], params: PageParams) -> tuple[list[Any], PageMeta]:
    """Run a SELECT with LIMIT/OFFSET and a matching COUNT. Returns (rows, meta).

    `stmt` must be ORDER BY-ed by the caller so pages are stable. Rows are ORM objects for
    single-entity selects (scalars) and Row tuples otherwise.
    """
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    result = db.execute(stmt.limit(params.limit).offset(params.offset))
    rows = result.scalars().all() if _single_entity(stmt) else result.all()
    meta = PageMeta(page=params.page, limit=params.limit, total=total, total_pages=math.ceil(total / params.limit))
    return list(rows), meta


def _single_entity(stmt: Select[Any]) -> bool:
    return len(stmt.column_descriptions) == 1 and stmt.column_descriptions[0].get("entity") is not None


def page_of(items: list[T], meta: PageMeta) -> dict[str, Any]:
    """Envelope {data, meta} for routers whose response_model is a Page schema."""
    return {"data": items, "meta": meta}
