"""Products and variants (contract: Products tag). Price edits never rewrite existing lines or invoices,
which keep their own snapshots."""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Product, ProductVariant, QuotationTemplateLine
from app.models.identity import User
from app.models.subscriptions import SubscriptionLine
from app.schemas.products import ProductInput, ProductOut, ProductUpdate, VariantInput, VariantOut, VariantUpdate

DUPLICATE_VARIANT = "This product already has a variant with that attribute and value"


def variant_out(v: ProductVariant) -> VariantOut:
    return VariantOut(
        id=v.id,
        product_id=v.product_id,
        attribute=v.attribute,
        value=v.value,
        extra_price=v.extra_price,
        is_archived=not v.is_active,
    )


def product_out(p: Product) -> ProductOut:
    variants = sorted(p.variants, key=lambda v: (v.created_at, v.id))
    return ProductOut(
        id=p.id,
        name=p.name,
        type=p.type,
        sales_price=p.sales_price,
        cost_price=p.cost_price,
        notes=p.notes,
        is_active=p.is_active,
        variants=[variant_out(v) for v in variants],
        created_at=p.created_at,
    )


def _get(db: Session, product_id: uuid.UUID, viewer: User | None = None) -> Product:
    """With a viewer, apply the customer rule: archived products do not exist for customers."""
    product = db.scalar(select(Product).where(Product.id == product_id).options(selectinload(Product.variants)))
    if product is None or (viewer is not None and viewer.role == "customer" and not product.is_active):
        raise AppError.not_found("Product not found")
    return product


def list_products(
    db: Session, viewer: User, params: PageParams, q: str | None, type_: str | None, is_active: bool | None
):
    stmt = select(Product).options(selectinload(Product.variants))
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q.strip()}%"))
    if type_:
        stmt = stmt.where(Product.type == type_)
    if viewer.role == "customer":
        stmt = stmt.where(Product.is_active.is_(True))
    elif is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    rows, meta = paginate(db, stmt.order_by(Product.created_at.desc(), Product.id), params)
    return [product_out(p) for p in rows], meta


def get_product(db: Session, viewer: User, product_id: uuid.UUID) -> ProductOut:
    return product_out(_get(db, product_id, viewer))


def create_product(db: Session, data: ProductInput) -> ProductOut:
    seen = set()
    for v in data.variants:
        key = (v.attribute.strip(), v.value.strip())
        if key in seen:
            raise AppError.conflict(DUPLICATE_VARIANT)
        seen.add(key)
    product = Product(
        name=data.name.strip(),
        type=data.type,
        sales_price=data.sales_price,
        cost_price=data.cost_price,
        notes=data.notes,
        is_active=data.is_active,
    )
    product.variants = [
        ProductVariant(attribute=v.attribute.strip(), value=v.value.strip(), extra_price=v.extra_price)
        for v in data.variants
    ]
    db.add(product)
    db.commit()
    return product_out(_get(db, product.id))


def update_product(db: Session, product_id: uuid.UUID, data: ProductUpdate) -> ProductOut:
    product = _get(db, product_id)
    changes = data.model_dump(exclude_unset=True)
    # Every column except notes is NOT NULL: an explicit null is a validation error, not "clear it".
    for field, value in changes.items():
        if value is None and field != "notes":
            raise AppError.validation(f"{field} cannot be null", field=field)
    for field, value in changes.items():
        setattr(product, field, value.strip() if field == "name" else value)
    db.commit()
    return product_out(_get(db, product_id))


def archive_product(db: Session, product_id: uuid.UUID) -> None:
    product = _get(db, product_id)
    product.is_active = False
    db.commit()


# ---------------------------------------------------------------- variants
def _get_variant(db: Session, product_id: uuid.UUID, variant_id: uuid.UUID) -> ProductVariant:
    variant = db.scalar(
        select(ProductVariant).where(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
    )
    if variant is None:
        raise AppError.not_found("Variant not found")
    return variant


def create_variant(db: Session, product_id: uuid.UUID, data: VariantInput) -> VariantOut:
    _get(db, product_id)
    variant = ProductVariant(
        product_id=product_id, attribute=data.attribute.strip(), value=data.value.strip(), extra_price=data.extra_price
    )
    db.add(variant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict(DUPLICATE_VARIANT) from None
    db.refresh(variant)
    return variant_out(variant)


def update_variant(db: Session, product_id: uuid.UUID, variant_id: uuid.UUID, data: VariantUpdate) -> VariantOut:
    variant = _get_variant(db, product_id, variant_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None:
            raise AppError.validation(f"{field} cannot be null", field=field)
        setattr(variant, field, value.strip() if isinstance(value, str) else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError.conflict(DUPLICATE_VARIANT) from None
    db.refresh(variant)
    return variant_out(variant)


def delete_variant(db: Session, product_id: uuid.UUID, variant_id: uuid.UUID) -> None:
    """Remove the variant, or archive it when a subscription line or quotation template still uses it."""
    variant = _get_variant(db, product_id, variant_id)
    on_subscription = db.scalar(select(SubscriptionLine.id).where(SubscriptionLine.variant_id == variant.id).limit(1))
    on_template = db.scalar(select(QuotationTemplateLine.id).where(QuotationTemplateLine.variant_id == variant.id).limit(1))
    if on_subscription is not None or on_template is not None:
        variant.is_active = False
    else:
        db.delete(variant)
    db.commit()
