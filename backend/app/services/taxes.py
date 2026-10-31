"""Tax rules (contract: Taxes tag). appliesToProductTypes <-> tax_product_types rows; no rows = every type.
Edits affect future invoices only: lines keep their own tax snapshot."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Tax, TaxProductType
from app.schemas.taxes import TaxInput, TaxOut, TaxUpdate

PERCENT_TOO_HIGH = "A percentage tax cannot exceed 100"


def to_out(t: Tax) -> TaxOut:
    return TaxOut(
        id=t.id,
        name=t.name,
        computation=t.computation,
        value=t.value,
        applies_to_product_types=sorted(pt.product_type for pt in t.product_types),
        is_active=t.is_active,
    )


def _get(db: Session, tax_id: uuid.UUID) -> Tax:
    tax = db.scalar(select(Tax).where(Tax.id == tax_id).options(selectinload(Tax.product_types)))
    if tax is None:
        raise AppError.not_found("Tax not found")
    return tax


def _check_value(computation: str, value) -> None:
    if computation == "percentage" and value > 100:
        raise AppError.business_rule(PERCENT_TOO_HIGH)


def list_taxes(db: Session, params: PageParams, is_active: bool | None):
    stmt = select(Tax).options(selectinload(Tax.product_types))
    if is_active is not None:
        stmt = stmt.where(Tax.is_active == is_active)
    rows, meta = paginate(db, stmt.order_by(Tax.created_at.desc(), Tax.id), params)
    return [to_out(t) for t in rows], meta


def get_tax(db: Session, tax_id: uuid.UUID) -> TaxOut:
    return to_out(_get(db, tax_id))


def create_tax(db: Session, data: TaxInput) -> TaxOut:
    _check_value(data.computation, data.value)
    tax = Tax(
        name=data.name.strip(), computation=data.computation, value=data.value, is_active=data.is_active
    )
    tax.product_types = [TaxProductType(product_type=t) for t in sorted(set(data.applies_to_product_types))]
    db.add(tax)
    db.commit()
    return to_out(_get(db, tax.id))


def update_tax(db: Session, tax_id: uuid.UUID, data: TaxUpdate) -> TaxOut:
    tax = _get(db, tax_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None:
            raise AppError.validation(f"{field} cannot be null", field=field)
    _check_value(changes.get("computation", tax.computation), changes.get("value", tax.value))
    types = changes.pop("applies_to_product_types", None)
    for field, value in changes.items():
        setattr(tax, field, value.strip() if field == "name" else value)
    if types is not None:
        wanted = set(types)
        have = {row.product_type for row in tax.product_types}
        # Explicit row changes: the relationship has no delete-orphan cascade (models are shared, not ours to edit).
        for row in list(tax.product_types):
            if row.product_type not in wanted:
                db.delete(row)
        db.add_all(TaxProductType(tax_id=tax.id, product_type=t) for t in sorted(wanted - have))
        db.flush()
        db.expire(tax, ["product_types"])
    db.commit()
    return to_out(_get(db, tax_id))


def deactivate_tax(db: Session, tax_id: uuid.UUID) -> None:
    tax = _get(db, tax_id)
    tax.is_active = False
    db.commit()
