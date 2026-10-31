"""Quotation templates (contract: Quotation Templates tag): a plan, product lines and a validity window.
Editing or deleting a template never touches subscriptions already created from it."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Plan, Product, ProductVariant, QuotationTemplate, QuotationTemplateLine
from app.schemas.templates import TemplateInput, TemplateLine, TemplateOut, TemplateUpdate

NOT_NULL_FIELDS = {"name", "plan_id", "validity_days", "lines"}


def to_out(t: QuotationTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        plan_id=t.plan_id,
        plan_name=t.plan.name,
        validity_days=t.validity_days,
        lines=[TemplateLine(product_id=ln.product_id, variant_id=ln.variant_id, quantity=ln.quantity) for ln in t.lines],
        notes=t.notes,
        created_at=t.created_at,
    )


def _select():
    return select(QuotationTemplate).options(selectinload(QuotationTemplate.plan), selectinload(QuotationTemplate.lines))


def _get(db: Session, template_id: uuid.UUID) -> QuotationTemplate:
    template = db.scalar(_select().where(QuotationTemplate.id == template_id).execution_options(populate_existing=True))
    if template is None:
        raise AppError.not_found("Quotation template not found")
    return template


def list_templates(db: Session, params: PageParams, q: str | None):
    stmt = _select()
    if q:
        stmt = stmt.where(QuotationTemplate.name.ilike(f"%{q.strip()}%"))
    rows, meta = paginate(db, stmt.order_by(QuotationTemplate.created_at.desc(), QuotationTemplate.id), params)
    return [to_out(t) for t in rows], meta


def get_template(db: Session, template_id: uuid.UUID) -> TemplateOut:
    return to_out(_get(db, template_id))


def _check_plan(db: Session, plan_id: uuid.UUID) -> None:
    if db.get(Plan, plan_id) is None:
        raise AppError.business_rule(f"Unknown plan: {plan_id}")


def _check_lines(db: Session, lines: list[TemplateLine]) -> None:
    """Every product exists and is active; a variant belongs to its product and is not archived."""
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_({ln.product_id for ln in lines})))}
    variant_ids = {ln.variant_id for ln in lines if ln.variant_id}
    variants = {v.id: v for v in db.scalars(select(ProductVariant).where(ProductVariant.id.in_(variant_ids)))}
    for i, ln in enumerate(lines):
        product = products.get(ln.product_id)
        if product is None:
            raise AppError.business_rule(f"lines[{i}]: unknown product {ln.product_id}")
        if not product.is_active:
            raise AppError.business_rule(f"lines[{i}]: product '{product.name}' is archived")
        if ln.variant_id is not None:
            variant = variants.get(ln.variant_id)
            if variant is None or variant.product_id != ln.product_id:
                raise AppError.business_rule(f"lines[{i}]: variant {ln.variant_id} does not belong to that product")
            if not variant.is_active:
                raise AppError.business_rule(f"lines[{i}]: variant {variant.attribute} {variant.value} is archived")


def _add_lines(db: Session, template_id: uuid.UUID, lines: list[TemplateLine]) -> None:
    db.add_all(
        QuotationTemplateLine(
            template_id=template_id, product_id=ln.product_id, variant_id=ln.variant_id, quantity=ln.quantity,
            sort_order=i,
        )
        for i, ln in enumerate(lines)
    )  # fmt: skip


def create_template(db: Session, data: TemplateInput) -> TemplateOut:
    _check_plan(db, data.plan_id)
    _check_lines(db, data.lines)
    template = QuotationTemplate(
        name=data.name.strip(), plan_id=data.plan_id, validity_days=data.validity_days, notes=data.notes
    )
    db.add(template)
    db.flush()
    _add_lines(db, template.id, data.lines)
    db.commit()
    return to_out(_get(db, template.id))


def update_template(db: Session, template_id: uuid.UUID, data: TemplateUpdate) -> TemplateOut:
    template = _get(db, template_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field in NOT_NULL_FIELDS:
            raise AppError.validation(f"{field} cannot be null", field=field)
    if "plan_id" in changes:
        _check_plan(db, changes["plan_id"])
    lines = data.lines if "lines" in changes else None
    if lines is not None:
        _check_lines(db, lines)
    for field in ("name", "plan_id", "validity_days", "notes"):
        if field in changes:
            value = changes[field]
            setattr(template, field, value.strip() if field == "name" else value)
    if lines is not None:
        db.flush()
        db.execute(delete(QuotationTemplateLine).where(QuotationTemplateLine.template_id == template.id))
        _add_lines(db, template.id, lines)
    db.commit()
    return to_out(_get(db, template_id))


def delete_template(db: Session, template_id: uuid.UUID) -> None:
    _get(db, template_id)
    # Bulk delete: the ORM relationship has no cascade, the database cascades the lines, and
    # subscriptions keep running (their template_id is set null).
    db.execute(delete(QuotationTemplate).where(QuotationTemplate.id == template_id))
    db.commit()
