"""Subscription CRUD, plan rules and the lifecycle state machine (API.md sections 2 and 3).

Reads go through v_subscriptions so subtotal/taxTotal/total are never computed in code. Every create and
transition writes subscription_status_history in the same transaction; transitions lock the row first.
"""
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import column, or_, select, table
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.pagination import PageParams, paginate
from app.models.catalogue import Plan, Product, ProductVariant, QuotationTemplate
from app.models.identity import Customer, User
from app.models.subscriptions import Subscription, SubscriptionLine, SubscriptionStatusHistory
from app.schemas.subscriptions import (
    CloseRequest,
    RenewRequest,
    SubscriptionInput,
    SubscriptionOut,
    SubscriptionRequest,
    SubscriptionUpdate,
)
from app.services import pricing
from app.services.periods import add_period

DEFAULT_QUOTATION_VALIDITY_DAYS = 30
EDITABLE = ("draft", "quotation")

# Lightweight handle on the view (not part of Base.metadata, so nothing can try to create it).
v_subscriptions = table(
    "v_subscriptions",
    *(
        column(c)
        for c in (
            "id", "number", "status", "is_paused", "customer_id", "customer_name", "customer_email", "plan_id",
            "plan_name", "billing_period", "allow_early_close", "allow_pause", "allow_renew", "template_id",
            "start_date", "expiry_date", "payment_terms", "quotation_valid_until", "next_billing_date",
            "subtotal", "tax_total", "total", "notes", "created_by", "created_at", "closed_at", "close_reason",
        )
    ),
)
v = v_subscriptions.c

# What a draft may still lack, with the contract's name for it (used in the 422 listing).
_REQUIRED_FOR_QUOTATION = (
    ("planId", "plan_id"),
    ("startDate", "start_date"),
    ("expiryDate", "expiry_date"),
    ("paymentTerms", "payment_terms"),
)


def _today() -> date:
    return date.today()


def _days(n: int) -> timedelta:
    return timedelta(days=n)


# ------------------------------------------------------------------ loading and scoping
def _find_locked(db: Session, subscription_id: uuid.UUID, user: User) -> Subscription:
    """SELECT ... FOR UPDATE. A customer only ever finds their own row; anyone else's is 404."""
    stmt = select(Subscription).where(Subscription.id == subscription_id).with_for_update()
    if user.role == "customer":
        stmt = stmt.where(Subscription.customer_id == user.customer_id)
    sub = db.scalars(stmt).first()
    if sub is None:
        raise AppError.not_found("Subscription not found")
    return sub


def _to_out(db: Session, rows: Sequence) -> list[SubscriptionOut]:
    ids = [r.id for r in rows]
    lines: dict[uuid.UUID, list[SubscriptionLine]] = {i: [] for i in ids}
    if ids:
        for line in db.scalars(
            select(SubscriptionLine)
            .where(SubscriptionLine.subscription_id.in_(ids))
            .order_by(SubscriptionLine.sort_order, SubscriptionLine.id)
        ):
            lines[line.subscription_id].append(line)
    return [
        SubscriptionOut.model_validate(
            {
                "id": r.id,
                "number": r.number,
                "status": r.status,
                "is_paused": r.is_paused,
                "customer": {"id": r.customer_id, "name": r.customer_name, "email": r.customer_email},
                "plan": None
                if r.plan_id is None
                else {
                    "id": r.plan_id,
                    "name": r.plan_name,
                    "billing_period": r.billing_period,
                    "allow_early_close": r.allow_early_close,
                    "allow_pause": r.allow_pause,
                    "allow_renew": r.allow_renew,
                },
                "template_id": r.template_id,
                "start_date": r.start_date,
                "expiry_date": r.expiry_date,
                "payment_terms": r.payment_terms,
                "quotation_valid_until": r.quotation_valid_until,
                "next_billing_date": r.next_billing_date,
                "lines": lines[r.id],
                "subtotal": r.subtotal,
                "tax_total": r.tax_total,
                "total": r.total,
                "notes": r.notes,
                "created_by": r.created_by,
                "created_at": r.created_at,
                "closed_at": r.closed_at,
                "close_reason": r.close_reason,
            }
        )
        for r in rows
    ]


def get_subscription(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    stmt = select(v_subscriptions).where(v.id == subscription_id)
    if user.role == "customer":
        stmt = stmt.where(v.customer_id == user.customer_id)
    row = db.execute(stmt).first()
    if row is None:
        raise AppError.not_found("Subscription not found")
    return _to_out(db, [row])[0]


def list_subscriptions(
    db: Session,
    user: User,
    params: PageParams,
    *,
    q: str | None = None,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    plan_id: uuid.UUID | None = None,
    expiring_before: date | None = None,
):
    stmt = select(v_subscriptions)
    if user.role == "customer":
        stmt = stmt.where(v.customer_id == user.customer_id)
    elif customer_id is not None:
        stmt = stmt.where(v.customer_id == customer_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(v.number.ilike(like), v.customer_name.ilike(like), v.customer_email.ilike(like)))
    if status:
        stmt = stmt.where(v.status == status)
    if plan_id is not None:
        stmt = stmt.where(v.plan_id == plan_id)
    if expiring_before is not None:
        stmt = stmt.where(v.expiry_date <= expiring_before)
    rows, meta = paginate(db, stmt.order_by(v.created_at.desc(), v.id), params)
    return _to_out(db, rows), meta


# ------------------------------------------------------------------ history
def _log(
    db: Session,
    sub: Subscription,
    event: str,
    user: User,
    from_status: str | None,
    note: str | None = None,
) -> None:
    db.add(
        SubscriptionStatusHistory(
            subscription_id=sub.id,
            event=event,
            from_status=from_status,
            to_status=sub.status,
            note=note,
            changed_by=user.id,
        )
    )


def list_history(db: Session, subscription_id: uuid.UUID, user: User, params: PageParams):
    get_subscription(db, subscription_id, user)  # 404 for unknown / someone else's
    h = SubscriptionStatusHistory
    stmt = (
        select(h, User.name.label("user_name"))
        .outerjoin(User, User.id == h.changed_by)
        .where(h.subscription_id == subscription_id)
        .order_by(h.changed_at.desc(), h.id.desc())
    )
    rows, meta = paginate(db, stmt, params)
    items = [
        {
            "id": r.SubscriptionStatusHistory.id,
            "event": r.SubscriptionStatusHistory.event,
            "from_status": r.SubscriptionStatusHistory.from_status,
            "to_status": r.SubscriptionStatusHistory.to_status,
            "changed_by": None
            if r.SubscriptionStatusHistory.changed_by is None
            else {"id": r.SubscriptionStatusHistory.changed_by, "name": r.user_name},
            "reason": r.SubscriptionStatusHistory.note,
            "created_at": r.SubscriptionStatusHistory.changed_at,
        }
        for r in rows
    ]
    return items, meta


# ------------------------------------------------------------------ plan rules and lines
def _check_plan(plan: Plan | None, start_date: date | None, quantities: Sequence[int]) -> None:
    """422 when the plan is inactive, startDate is outside its window or a line is under minQuantity."""
    if plan is None:
        return
    problems: list[str] = []
    if not plan.is_active:
        problems.append(f"Plan '{plan.name}' is not active")
    if start_date is not None:
        if start_date < plan.available_from:
            problems.append(f"Plan '{plan.name}' is available from {plan.available_from}")
        if plan.available_to is not None and start_date > plan.available_to:
            problems.append(f"Plan '{plan.name}' is available until {plan.available_to}")
    if any(qty < plan.min_quantity for qty in quantities):
        problems.append(f"Plan '{plan.name}' needs a quantity of at least {plan.min_quantity} per line")
    if problems:
        raise AppError.business_rule("; ".join(problems), [{"field": "planId", "message": p} for p in problems])


def _check_dates(start_date: date | None, expiry_date: date | None) -> None:
    if start_date is not None and expiry_date is not None and expiry_date <= start_date:
        raise AppError.business_rule("expiryDate must be after startDate")


def _require_plan(db: Session, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise AppError.validation("Plan not found", "planId")
    return plan


def _require_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise AppError.validation("Customer not found", "customerId")
    return customer


def _build_lines(
    db: Session, specs: Sequence[tuple[uuid.UUID, uuid.UUID | None, int, Decimal | None]]
) -> list[SubscriptionLine]:
    """Resolve, price and tax each line. specs: (product_id, variant_id, quantity, unit price override)."""
    taxes = pricing.load_active_taxes(db)
    lines: list[SubscriptionLine] = []
    for i, (product_id, variant_id, quantity, override) in enumerate(specs):
        field = f"lines.{i}"
        product = db.get(Product, product_id)
        if product is None:
            raise AppError.validation("Product not found", f"{field}.productId")
        if not product.is_active:
            raise AppError.business_rule(
                f"Product '{product.name}' is archived",
                [{"field": f"{field}.productId", "message": "Product is archived"}],
            )
        variant = None
        if variant_id is not None:
            variant = db.get(ProductVariant, variant_id)
            if variant is None or variant.product_id != product.id:
                raise AppError.validation("Variant does not belong to this product", f"{field}.variantId")
            if not variant.is_active:
                raise AppError.business_rule(
                    f"Variant '{variant.value}' is no longer available",
                    [{"field": f"{field}.variantId", "message": "Variant is not available"}],
                )
        priced = pricing.price_line(product, variant, quantity, taxes, override)
        lines.append(
            SubscriptionLine(
                product_id=product.id,
                variant_id=variant.id if variant else None,
                product_name=product.name,
                variant_label=f"{variant.attribute} {variant.value}" if variant else None,
                quantity=quantity,
                unit_price=priced.unit_price,
                tax_id=priced.tax_id,
                tax_name=priced.tax_name,
                tax_rate=priced.tax_rate,
                tax_amount=priced.tax_amount,
                sort_order=i,
            )
        )
    return lines


# ------------------------------------------------------------------ create / update / delete
def create_subscription(db: Session, body: SubscriptionInput, user: User) -> SubscriptionOut:
    _require_customer(db, body.customer_id)

    template = None
    if body.template_id is not None:
        template = db.get(QuotationTemplate, body.template_id)
        if template is None:
            raise AppError.validation("Quotation template not found", "templateId")

    plan_id = body.plan_id or (template.plan_id if template else None)
    plan = _require_plan(db, plan_id) if plan_id else None

    if body.lines is not None:
        specs = [(ln.product_id, ln.variant_id, ln.quantity, ln.unit_price) for ln in body.lines]
    elif template is not None:
        specs = [(ln.product_id, ln.variant_id, ln.quantity, None) for ln in template.lines]
    else:
        specs = []
    lines = _build_lines(db, specs)

    _check_plan(plan, body.start_date, [ln.quantity for ln in lines])
    _check_dates(body.start_date, body.expiry_date)

    sub = Subscription(
        customer_id=body.customer_id,
        plan_id=plan.id if plan else None,
        template_id=template.id if template else None,
        start_date=body.start_date,
        expiry_date=body.expiry_date,
        payment_terms=body.payment_terms,
        quotation_valid_until=_today() + _days(template.validity_days) if template else None,
        notes=body.notes if body.notes is not None else (template.notes if template else None),
        created_by=user.id,
        lines=lines,
    )
    db.add(sub)
    db.flush()  # assigns the id and the DB-generated number
    _log(db, sub, "created", user, None)
    db.commit()
    return get_subscription(db, sub.id, user)


def request_subscription(db: Session, body: SubscriptionRequest, user: User) -> SubscriptionOut:
    """Customer self-service: a draft for the caller only, catalogue prices, no override."""
    if user.customer_id is None:
        raise AppError.forbidden("This account has no customer record")
    plan = _require_plan(db, body.plan_id)
    lines = _build_lines(db, [(ln.product_id, ln.variant_id, ln.quantity, None) for ln in body.lines])
    _check_plan(plan, body.start_date, [ln.quantity for ln in lines])

    sub = Subscription(
        customer_id=user.customer_id,
        plan_id=plan.id,
        start_date=body.start_date,
        notes=body.notes,
        created_by=user.id,
        lines=lines,
    )
    db.add(sub)
    db.flush()
    _log(db, sub, "created", user, None)
    db.commit()
    return get_subscription(db, sub.id, user)


def update_subscription(
    db: Session, subscription_id: uuid.UUID, body: SubscriptionUpdate, user: User
) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    if sub.status not in EDITABLE:
        raise AppError.conflict(f"A {sub.status} subscription can no longer be edited")
    sent = body.model_fields_set

    if "customer_id" in sent:
        sub.customer_id = _require_customer(db, body.customer_id).id
    if "plan_id" in sent:
        sub.plan_id = _require_plan(db, body.plan_id).id
    for name in ("start_date", "expiry_date", "payment_terms", "notes"):
        if name in sent:
            setattr(sub, name, getattr(body, name))

    if "lines" in sent:
        new_lines = _build_lines(db, [(ln.product_id, ln.variant_id, ln.quantity, ln.unit_price) for ln in body.lines])
        for old in list(sub.lines):
            db.delete(old)
        db.flush()
        sub.lines = new_lines

    _check_plan(db.get(Plan, sub.plan_id) if sub.plan_id else None, sub.start_date, [ln.quantity for ln in sub.lines])
    _check_dates(sub.start_date, sub.expiry_date)
    db.commit()
    return get_subscription(db, sub.id, user)


def delete_subscription(db: Session, subscription_id: uuid.UUID, user: User) -> None:
    sub = _find_locked(db, subscription_id, user)
    if sub.status != "draft":
        raise AppError.conflict("Only a draft subscription can be deleted")
    db.delete(sub)
    db.commit()


# ------------------------------------------------------------------ transitions
def _require_status(sub: Subscription, expected: str, action: str) -> None:
    if sub.status != expected:
        raise AppError.conflict(f"Cannot {action}: subscription is {sub.status}, expected {expected}")


def _plan_of(db: Session, sub: Subscription) -> Plan:
    plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
    if plan is None:
        raise AppError.business_rule("Subscription has no plan", [{"field": "planId", "message": "Required"}])
    return plan


def _move(db: Session, sub: Subscription, to_status: str, user: User, note: str | None = None) -> None:
    from_status = sub.status
    sub.status = to_status
    _log(db, sub, "status_change", user, from_status, note)


def send_quotation(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "draft", "send quotation")

    missing = [api for api, attr in _REQUIRED_FOR_QUOTATION if getattr(sub, attr) is None]
    if not sub.lines:
        missing.append("lines")
    if missing:
        raise AppError.business_rule(
            "Cannot send quotation, missing: " + ", ".join(missing),
            [{"field": f, "message": "Required to send a quotation"} for f in missing],
        )
    _check_dates(sub.start_date, sub.expiry_date)
    _check_plan(_plan_of(db, sub), sub.start_date, [ln.quantity for ln in sub.lines])

    template = db.get(QuotationTemplate, sub.template_id) if sub.template_id else None
    sub.quotation_valid_until = _today() + _days(template.validity_days if template else DEFAULT_QUOTATION_VALIDITY_DAYS)
    _move(db, sub, "quotation", user)
    db.commit()
    return get_subscription(db, sub.id, user)


def confirm(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "quotation", "confirm")
    if sub.quotation_valid_until is not None and sub.quotation_valid_until < _today():
        raise AppError.business_rule(f"The quotation expired on {sub.quotation_valid_until}")
    _check_plan(_plan_of(db, sub), sub.start_date, [ln.quantity for ln in sub.lines])
    _move(db, sub, "confirmed", user)  # from here on lines and totals are locked (update is 409)
    db.commit()
    return get_subscription(db, sub.id, user)


def activate(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "confirmed", "activate")
    missing = [api for api, attr in _REQUIRED_FOR_QUOTATION[:3] if getattr(sub, attr) is None]
    if missing:
        raise AppError.business_rule(
            "Cannot activate, missing: " + ", ".join(missing),
            [{"field": f, "message": "Required to activate"} for f in missing],
        )
    sub.next_billing_date = sub.start_date
    _move(db, sub, "active", user)
    db.commit()
    return get_subscription(db, sub.id, user)


def close(db: Session, subscription_id: uuid.UUID, body: CloseRequest | None, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "active", "close")
    if not _plan_of(db, sub).allow_early_close:
        raise AppError.business_rule("This plan does not allow early close")
    reason = body.reason if body else None
    sub.closed_at = datetime.now(timezone.utc)
    sub.close_reason = reason
    sub.next_billing_date = None
    _move(db, sub, "closed", user, reason)
    db.commit()
    return get_subscription(db, sub.id, user)


def pause(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "active", "pause")
    if sub.is_paused:
        raise AppError.conflict("Subscription is already paused")
    if not _plan_of(db, sub).allow_pause:
        raise AppError.business_rule("This plan does not allow pausing")
    sub.is_paused = True
    _log(db, sub, "paused", user, sub.status)
    db.commit()
    return get_subscription(db, sub.id, user)


def resume(db: Session, subscription_id: uuid.UUID, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    if not sub.is_paused:
        raise AppError.conflict("Subscription is not paused")
    # Paused time is never billed: nextBillingDate never moves back, and jumps to today if it has passed.
    sub.next_billing_date = max(sub.next_billing_date or _today(), _today())
    sub.is_paused = False
    _log(db, sub, "resumed", user, sub.status)
    db.commit()
    return get_subscription(db, sub.id, user)


def renew(db: Session, subscription_id: uuid.UUID, body: RenewRequest | None, user: User) -> SubscriptionOut:
    sub = _find_locked(db, subscription_id, user)
    _require_status(sub, "active", "renew")
    plan = _plan_of(db, sub)
    if not plan.allow_renew:
        raise AppError.business_rule("This plan does not allow renewal")
    new_expiry = (
        body.new_expiry_date if body and body.new_expiry_date else add_period(sub.expiry_date, plan.billing_period)
    )
    if new_expiry <= sub.expiry_date:
        raise AppError.business_rule("newExpiryDate must be after the current expiry date")
    old = sub.expiry_date
    sub.expiry_date = new_expiry
    _log(db, sub, "renewed", user, sub.status, f"Expiry {old} -> {new_expiry}")
    db.commit()
    return get_subscription(db, sub.id, user)
