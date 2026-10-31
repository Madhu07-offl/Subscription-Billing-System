"""Discount rules (contract: Discounts tag, API.md rule 6). Rules only: applying a discount to an invoice and
the usage ledger belong to billing. discounts.used_count is database-owned and is never written here;
status comes from v_discounts."""
import uuid
from datetime import date

from sqlalchemy import Select, String, column, delete, or_, select, table
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Product
from app.models.discounts import Discount, DiscountProduct, DiscountSubscription
from app.models.subscriptions import Subscription
from app.schemas.discounts import DiscountInput, DiscountOut, DiscountUpdate

_v_discounts = table("v_discounts", column("id"), column("status", String))

NOT_NULL_FIELDS = {"name", "type", "value", "scope", "start_date", "is_active"}
SCALARS = (
    "name", "type", "value", "scope", "min_purchase_amount", "min_quantity",
    "start_date", "end_date", "usage_limit", "is_active",
)  # fmt: skip


def _select() -> Select:
    return (
        select(Discount, _v_discounts.c.status)
        .join(_v_discounts, _v_discounts.c.id == Discount.id)
        .options(selectinload(Discount.products), selectinload(Discount.subscriptions))
    )


def to_out(row) -> DiscountOut:
    d, status = row
    return DiscountOut(
        id=d.id,
        name=d.name,
        type=d.type,
        value=d.value,
        scope=d.scope,
        min_purchase_amount=d.min_purchase_amount,
        min_quantity=d.min_quantity,
        start_date=d.start_date,
        end_date=d.end_date,
        usage_limit=d.usage_limit,
        used_count=d.used_count,
        status=status,
        product_ids=sorted(p.product_id for p in d.products),
        subscription_ids=sorted(s.subscription_id for s in d.subscriptions),
        is_active=d.is_active,
    )


def _load(db: Session, discount_id: uuid.UUID) -> DiscountOut:
    row = db.execute(
        _select().where(Discount.id == discount_id).execution_options(populate_existing=True)
    ).first()
    if row is None:
        raise AppError.not_found("Discount not found")
    return to_out(row)


def list_discounts(db: Session, params: PageParams, q: str | None, is_active: bool | None, valid_on: date | None):
    stmt = _select()
    if q:
        stmt = stmt.where(Discount.name.ilike(f"%{q.strip()}%"))
    if is_active is not None:
        stmt = stmt.where(Discount.is_active == is_active)
    if valid_on is not None:
        stmt = stmt.where(
            Discount.is_active.is_(True),
            Discount.start_date <= valid_on,
            or_(Discount.end_date.is_(None), Discount.end_date >= valid_on),
            or_(Discount.usage_limit.is_(None), Discount.used_count < Discount.usage_limit),
        )
    rows, meta = paginate(db, stmt.order_by(Discount.created_at.desc(), Discount.id), params)
    return [to_out(r) for r in rows], meta


def get_discount(db: Session, discount_id: uuid.UUID) -> DiscountOut:
    return _load(db, discount_id)


# ------------------------------------------------------------------ rules
def _check_rules(
    type_: str, value, start: date, end: date | None, usage_limit: int | None, used_count: int = 0
) -> None:
    if type_ == "percentage" and value > 100:
        raise AppError.business_rule("A percentage discount must be between 0 and 100")
    if end is not None and end < start:
        raise AppError.business_rule("endDate cannot be before startDate")
    if usage_limit is not None and usage_limit < used_count:
        raise AppError.business_rule(f"usageLimit cannot be lower than usedCount ({used_count})")


def _require_existing(db: Session, model, ids: list[uuid.UUID], label: str) -> list[uuid.UUID]:
    wanted = set(ids)
    if wanted:
        found = set(db.scalars(select(model.id).where(model.id.in_(wanted))))
        if missing := wanted - found:
            raise AppError.business_rule(f"Unknown {label}: {', '.join(sorted(str(m) for m in missing))}")
    return sorted(wanted)


def _replace_links(
    db: Session, discount: Discount, scope: str, product_ids: list[uuid.UUID], subscription_ids: list[uuid.UUID]
) -> None:
    """Only the links that match the scope are kept: products for scope=products, subscriptions otherwise
    (no subscription rows = all subscriptions)."""
    if scope == "products":
        if not product_ids:
            raise AppError.business_rule("A products-scope discount needs at least one product")
        product_ids = _require_existing(db, Product, product_ids, "product")
        subscription_ids = []
    else:
        subscription_ids = _require_existing(db, Subscription, subscription_ids, "subscription")
        product_ids = []
    db.execute(delete(DiscountProduct).where(DiscountProduct.discount_id == discount.id))
    db.execute(delete(DiscountSubscription).where(DiscountSubscription.discount_id == discount.id))
    db.add_all(DiscountProduct(discount_id=discount.id, product_id=p) for p in product_ids)
    db.add_all(DiscountSubscription(discount_id=discount.id, subscription_id=s) for s in subscription_ids)


def create_discount(db: Session, data: DiscountInput) -> DiscountOut:
    _check_rules(data.type, data.value, data.start_date, data.end_date, data.usage_limit)
    discount = Discount(
        name=data.name.strip(),
        type=data.type,
        value=data.value,
        scope=data.scope,
        min_purchase_amount=data.min_purchase_amount,
        min_quantity=data.min_quantity,
        start_date=data.start_date,
        end_date=data.end_date,
        usage_limit=data.usage_limit,
        is_active=data.is_active,
    )
    db.add(discount)
    db.flush()
    _replace_links(db, discount, data.scope, data.product_ids, data.subscription_ids)
    db.commit()
    return _load(db, discount.id)


def update_discount(db: Session, discount_id: uuid.UUID, data: DiscountUpdate) -> DiscountOut:
    discount = db.scalar(
        select(Discount)
        .where(Discount.id == discount_id)
        .options(selectinload(Discount.products), selectinload(Discount.subscriptions))
        .with_for_update()  # a concurrent billing run moves used_count; check the limit against the locked row
    )
    if discount is None:
        raise AppError.not_found("Discount not found")
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field in NOT_NULL_FIELDS | {"product_ids", "subscription_ids"}:
            raise AppError.validation(f"{field} cannot be null", field=field)
    merged = {f: changes.get(f, getattr(discount, f)) for f in SCALARS}
    _check_rules(
        merged["type"], merged["value"], merged["start_date"], merged["end_date"], merged["usage_limit"],
        discount.used_count,
    )  # fmt: skip

    scope_changed = merged["scope"] != discount.scope
    product_ids = changes.get("product_ids")
    subscription_ids = changes.get("subscription_ids")
    if product_ids is None:
        product_ids = [p.product_id for p in discount.products]
    if subscription_ids is None:
        subscription_ids = [] if scope_changed else [s.subscription_id for s in discount.subscriptions]

    for field in SCALARS:
        if field in changes:
            setattr(discount, field, merged[field].strip() if field == "name" else merged[field])
    db.flush()
    if scope_changed or "product_ids" in changes or "subscription_ids" in changes:
        _replace_links(db, discount, merged["scope"], product_ids, subscription_ids)
    db.commit()
    return _load(db, discount_id)


def deactivate_discount(db: Session, discount_id: uuid.UUID) -> None:
    discount = db.get(Discount, discount_id)
    if discount is None:
        raise AppError.not_found("Discount not found")
    discount.is_active = False
    db.commit()
