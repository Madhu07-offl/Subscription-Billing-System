import uuid

from fastapi import APIRouter, Response

from app.core.deps import CurrentUser, DbSession
from app.services import invoice_pdf

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get(
    "/{id}/print",
    response_class=Response,
    responses={200: {"description": "PDF file", "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}},
)
def print_invoice(id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    pdf, filename = invoice_pdf.print_invoice(db, id, user)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})
