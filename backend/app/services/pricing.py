"""Line pricing, tax and discounts (API.md section 3, rules 3 and 5-7). Pure functions plus two loaders, so the
subscription service, the billing run and invoice corrections all price lines the same way."""
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalogue import Product, ProductVariant, Tax
from app.models.discounts import Discount

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Round half up to 2 decimals."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricedLine:
    unit_price: Decimal
    amount: Decimal  # quantity * unit_price, before tax
    tax_id: uuid.UUID | None
    tax_name: str | None
    tax_rate: Decimal | None  # percent, or the fixed amount for computation=fixed
    tax_amount: Decimal


def unit_price(product: Product, variant: ProductVariant | None, override: Decimal | None = None) -> Decimal:
    """product.sales_price + variant.extra_price unless the caller overrides it (rule 3)."""
    if override is not None:
        return money(override)
    return money(product.sales_price + (variant.extra_price if variant is not None else 0))


def load_active_taxes(db: Session) -> list[Tax]:
    return list(
        db.scalars(
            select(Tax)
            .where(Tax.is_active.is_(True))
            .options(selectinload(Tax.product_types))
            .order_by(Tax.created_at, Tax.id)
        )
    )


def pick_tax(taxes: list[Tax], product_type: str) -> Tax | None:
    """Active tax whose product types contain `product_type`; a tax with no types applies to all.
    A type-specific tax beats an all-types one; ties go to the oldest tax (taxes arrive oldest first)."""
    specific = [t for t in taxes if any(pt.product_type == product_type for pt in t.product_types)]
    generic = [t for t in taxes if not t.product_types]
    chosen = specific or generic
    return chosen[0] if chosen else None


def compute_tax(computation: str | None, value: Decimal | None, amount: Decimal) -> Decimal:
    """percentage: amount * value / 100; fixed: value per line. Half up, 2dp, per line.
    `amount` is what the tax is charged on (after any discount, rule 7)."""
    if computation is None or value is None:
        return Decimal("0.00")
    if computation == "fixed":
        return money(value)
    return money(amount * value / 100)


def tax_amount(tax: Tax | None, amount: Decimal) -> Decimal:
    return compute_tax(tax.computation if tax else None, tax.value if tax else None, amount)


def price_line(
    product: Product,
    variant: ProductVariant | None,
    quantity: int,
    taxes: list[Tax],
    override: Decimal | None = None,
) -> PricedLine:
    price = unit_price(product, variant, override)
    amount = money(price * quantity)
    tax = pick_tax(taxes, product.type)
    return PricedLine(
        unit_price=price,
        amount=amount,
        tax_id=tax.id if tax else None,
        tax_name=tax.name if tax else None,
        tax_rate=tax.value if tax else None,
        tax_amount=tax_amount(tax, amount),
    )


# ------------------------------------------------------------------------------------------ discounts (rule 6)
@dataclass(frozen=True)
class DiscountLine:
    """What the discount engine needs to know about one line."""

    product_id: uuid.UUID
    quantity: int
    amount: Decimal  # quantity * unit_price, before discount


@dataclass(frozen=True)
class AppliedDiscount:
    discount_id: uuid.UUID
    name: str
    amount: Decimal


def load_candidate_discounts(db: Session, period_start: date, *, lock: bool = False) -> list[Discount]:
    """Active discounts whose date window contains `period_start`, oldest first (so ties are stable).
    populate_existing refreshes used_count, which the DB trigger changes while a run is in progress.
    lock=True takes row locks so two concurrent runs cannot both spend the last use of a discount."""
    stmt = (
        select(Discount)
        .where(
            Discount.is_active.is_(True),
            Discount.start_date <= period_start,
            or_(Discount.end_date.is_(None), Discount.end_date >= period_start),
        )
        .options(selectinload(Discount.products), selectinload(Discount.subscriptions))
        .order_by(Discount.created_at, Discount.id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update(of=Discount)
    return list(db.scalars(stmt))


def discount_is_open(d: Discount, period_start: date, held: Collection[uuid.UUID] = ()) -> bool:
    """Active, startDate <= period start <= endDate, usedCount < usageLimit.
    `held` = discounts this invoice already uses: their own usage is inside used_count, so it must not
    block re-pricing the same invoice."""
    if not d.is_active or d.start_date > period_start:
        return False
    if d.end_date is not None and period_start > d.end_date:
        return False
    if d.usage_limit is not None and d.used_count >= d.usage_limit and d.id not in held:
        return False
    return True


def _meets_minimums(d: Discount, quantity: int, amount: Decimal) -> bool:
    if d.min_quantity is not None and quantity < d.min_quantity:
        return False
    if d.min_purchase_amount is not None and amount < d.min_purchase_amount:
        return False
    return True


def _one_line_discount(d: Discount, amount: Decimal) -> Decimal:
    """percentage: amount * value / 100; fixed: value, never more than the line itself."""
    if d.type == "percentage":
        return min(money(amount * d.value / 100), amount)
    return min(money(d.value), amount)


def _share_fixed(value: Decimal, amounts: Sequence[Decimal]) -> list[Decimal]:
    """Split a fixed subscription-scope discount over the lines in proportion to their amounts. Each share is
    rounded half up; the rounding remainder goes on the last line (rule 6)."""
    subtotal = sum(amounts, Decimal("0"))
    if subtotal <= 0:
        return [Decimal("0.00")] * len(amounts)
    total = min(money(value), subtotal)
    shares = [money(total * a / subtotal) for a in amounts[:-1]]
    last = max(total - sum(shares, Decimal("0")), Decimal("0.00"))
    shares.append(min(last, amounts[-1]))
    return shares


def _discount_per_line(
    d: Discount, lines: Sequence[DiscountLine], subscription_id: uuid.UUID | None
) -> list[Decimal]:
    zero = Decimal("0.00")
    if d.scope == "products":
        product_ids = {link.product_id for link in d.products}
        return [
            _one_line_discount(d, ln.amount)
            if ln.product_id in product_ids and _meets_minimums(d, ln.quantity, ln.amount)
            else zero
            for ln in lines
        ]
    # scope = subscriptions; no link rows = every subscription
    linked = {link.subscription_id for link in d.subscriptions}
    if linked and subscription_id not in linked:
        return [zero] * len(lines)
    amounts = [ln.amount for ln in lines]
    if not _meets_minimums(d, sum(ln.quantity for ln in lines), sum(amounts, Decimal("0"))):
        return [zero] * len(lines)
    if d.type == "fixed":
        return _share_fixed(d.value, amounts)
    return [_one_line_discount(d, a) for a in amounts]


def pick_discounts(
    lines: Sequence[DiscountLine],
    discounts: Sequence[Discount],
    subscription_id: uuid.UUID | None,
    period_start: date,
    held: Collection[uuid.UUID] = (),
) -> list[AppliedDiscount | None]:
    """One entry per line: the winning discount (the largest amount; on a tie the oldest rule) or None."""
    best: list[AppliedDiscount | None] = [None] * len(lines)
    for d in discounts:
        if not discount_is_open(d, period_start, held):
            continue
        for i, amount in enumerate(_discount_per_line(d, lines, subscription_id)):
            if amount > 0 and (best[i] is None or amount > best[i].amount):
                best[i] = AppliedDiscount(d.id, d.name, amount)
    return best


# --------------------------------------------------------------------------------------------- invoice totals
@dataclass(frozen=True)
class InvoiceLineDraft:
    """An invoice line before discount and tax. The tax columns are the snapshot taken on the subscription line."""

    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    tax_computation: str | None = None
    tax_rate: Decimal | None = None


@dataclass(frozen=True)
class InvoiceLinePriced:
    discount: AppliedDiscount | None
    discount_amount: Decimal
    tax_amount: Decimal
    amount: Decimal  # quantity * unit_price - discount_amount, before tax (matches the generated column)


@dataclass(frozen=True)
class InvoiceTotals:
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal


def price_invoice(
    drafts: Sequence[InvoiceLineDraft],
    discounts: Sequence[Discount],
    subscription_id: uuid.UUID | None,
    period_start: date,
    held: Collection[uuid.UUID] = (),
) -> tuple[list[InvoiceLinePriced], InvoiceTotals]:
    """Rules 6 and 7: discount per line, tax on the discounted amount, total = subtotal - discount + tax.
    plan.price is never involved."""
    gross = [money(d.quantity * d.unit_price) for d in drafts]
    winners = pick_discounts(
        [DiscountLine(d.product_id, d.quantity, g) for d, g in zip(drafts, gross)],
        discounts,
        subscription_id,
        period_start,
        held,
    )
    priced: list[InvoiceLinePriced] = []
    for d, g, win in zip(drafts, gross, winners):
        off = win.amount if win else Decimal("0.00")
        net = g - off
        priced.append(InvoiceLinePriced(win, off, compute_tax(d.tax_computation, d.tax_rate, net), net))
    subtotal = sum(gross, Decimal("0.00"))
    discount_total = sum((p.discount_amount for p in priced), Decimal("0.00"))
    tax_total = sum((p.tax_amount for p in priced), Decimal("0.00"))
    return priced, InvoiceTotals(subtotal, discount_total, tax_total, subtotal - discount_total + tax_total)
