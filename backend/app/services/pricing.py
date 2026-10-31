"""Line pricing and tax (API.md section 3, rules 3, 5 and 7). Pure functions plus one tax loader, so the
subscription service and the billing run price lines the same way."""
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalogue import Product, ProductVariant, Tax

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


def tax_amount(tax: Tax | None, amount: Decimal) -> Decimal:
    """percentage: amount * value / 100; fixed: value per line. Half up, 2dp, per line."""
    if tax is None:
        return Decimal("0.00")
    if tax.computation == "fixed":
        return money(tax.value)
    return money(amount * tax.value / 100)


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
