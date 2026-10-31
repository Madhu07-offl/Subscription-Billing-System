import uuid

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import DbSession, require_roles
from app.core.pagination import Pagination, page_of
from app.schemas.templates import TemplateInput, TemplateList, TemplateOut, TemplateUpdate
from app.services import templates as template_service

router = APIRouter(prefix="/quotation-templates", tags=["Quotation Templates"])

AdminOnly = Depends(require_roles("admin"))
AdminOrStaff = Depends(require_roles("admin", "staff"))


@router.get("", response_model=TemplateList, dependencies=[AdminOrStaff])
def list_templates(db: DbSession, params: Pagination, q: str | None = None):
    rows, meta = template_service.list_templates(db, params, q)
    return page_of(rows, meta)


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED, dependencies=[AdminOnly])
def create_template(body: TemplateInput, db: DbSession):
    return template_service.create_template(db, body)


@router.get("/{template_id}", response_model=TemplateOut, dependencies=[AdminOrStaff])
def get_template(template_id: uuid.UUID, db: DbSession):
    return template_service.get_template(db, template_id)


@router.patch("/{template_id}", response_model=TemplateOut, dependencies=[AdminOnly])
def update_template(template_id: uuid.UUID, body: TemplateUpdate, db: DbSession):
    return template_service.update_template(db, template_id, body)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[AdminOnly])
def delete_template(template_id: uuid.UUID, db: DbSession):
    template_service.delete_template(db, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
