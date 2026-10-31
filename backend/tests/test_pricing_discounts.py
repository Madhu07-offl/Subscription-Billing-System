"""Pure tests of the discount engine (API.md rules 6 and 7): no database needed."""
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services import pricing
from app.services.pricing import DiscountLine, InvoiceLineDraft

D = Decimal
PERIOD = date(2026, 6, 1)
SUB = uuid.uuid4()
P1, P2, P3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def discount(
    *,
    type="percentage",
    value="10",
    scope="products",
    products=(),
    subscriptions=(),
    min_quantity=None,
    min_purchase_amount=None,
    start_date=date(2026, 1, 1),
    end_date=None,
    usage_limit=None,
    used_count=0,
    is_active=True,
    name=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name or f"{type}-{value}",
        type=type,
        value=D(value),
        scope=scope,
        products=[SimpleNamespace(product_id=p) for p in products],
        subscriptions=[SimpleNamespace(subscription_id=s) for s in subscriptions],
        min_quantity=min_quantity,
        min_purchase_amount=None if min_purchase_amount is None else D(min_purchase_amount),
        start_date=start_date,
        end_date=end_date,
        usage_limit=usage_limit,
        used_count=used_count,
        is_active=is_active,
    )


def lines(*specs):
    """(product, quantity, amount) -> DiscountLine"""
    return [DiscountLine(p, q, D(a)) for p, q, a in specs]


def amounts(winners):
    return [w.amount if w else None for w in winners]


# ------------------------------------------------------------------ eligibility
def test_inactive_expired_scheduled_and_exhausted_discounts_do_not_apply():
    ls = lines((P1, 1, "100.00"))
    for d in (
        discount(products=[P1], is_active=False),
        discount(products=[P1], start_date=date(2026, 6, 2)),  # starts after the period start
        discount(products=[P1], end_date=date(2026, 5, 31)),  # ended before the period start
        discount(products=[P1], usage_limit=3, used_count=3),
    ):
        assert pricing.pick_discounts(ls, [d], SUB, PERIOD) == [None]


def test_boundary_dates_are_inclusive_and_open_limit_applies():
    ls = lines((P1, 1, "100.00"))
    d = discount(products=[P1], start_date=PERIOD, end_date=PERIOD, usage_limit=3, used_count=2)
    assert amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD)) == [D("10.00")]


def test_held_discount_is_not_blocked_by_its_own_usage():
    ls = lines((P1, 1, "100.00"))
    d = discount(products=[P1], usage_limit=1, used_count=1)
    assert pricing.pick_discounts(ls, [d], SUB, PERIOD) == [None]
    assert amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD, held={d.id})) == [D("10.00")]


# ------------------------------------------------------------------ products scope
def test_products_scope_touches_only_listed_products_with_per_line_minimums():
    d = discount(products=[P1], min_quantity=2, min_purchase_amount="150")
    ls = lines((P1, 2, "200.00"), (P1, 1, "300.00"), (P2, 5, "500.00"), (P1, 2, "100.00"))
    # line 0 qualifies; line 1 is under min quantity; line 2 is another product; line 3 is under the min amount
    assert amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD)) == [D("20.00"), None, None, None]


def test_fixed_products_discount_applies_once_per_matching_line_and_never_exceeds_the_line():
    d = discount(type="fixed", value="50", products=[P1, P2])
    ls = lines((P1, 1, "100.00"), (P2, 1, "30.00"), (P3, 1, "100.00"))
    assert amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD)) == [D("50.00"), D("30.00"), None]


# ------------------------------------------------------------------ subscriptions scope
def test_subscriptions_scope_without_links_applies_to_every_subscription():
    d = discount(scope="subscriptions", value="10")
    ls = lines((P1, 1, "100.00"), (P2, 1, "50.00"))
    assert amounts(pricing.pick_discounts(ls, [d], uuid.uuid4(), PERIOD)) == [D("10.00"), D("5.00")]


def test_subscriptions_scope_with_links_applies_only_to_those_subscriptions():
    d = discount(scope="subscriptions", subscriptions=[SUB])
    ls = lines((P1, 1, "100.00"))
    assert amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD)) == [D("10.00")]
    assert pricing.pick_discounts(ls, [d], uuid.uuid4(), PERIOD) == [None]


def test_subscription_minimums_use_total_quantity_and_subtotal():
    d = discount(scope="subscriptions", min_quantity=3, min_purchase_amount="150")
    # total quantity 2 < 3
    assert pricing.pick_discounts(lines((P1, 1, "100.00"), (P2, 1, "60.00")), [d], SUB, PERIOD) == [None, None]
    # quantity 3 but subtotal 140.00 < 150.00
    assert pricing.pick_discounts(lines((P1, 2, "100.00"), (P2, 1, "40.00")), [d], SUB, PERIOD) == [None, None]
    # quantity 3 and subtotal 160.00: both minimums met, so every line is discounted
    got = pricing.pick_discounts(lines((P1, 2, "100.00"), (P2, 1, "60.00")), [d], SUB, PERIOD)
    assert amounts(got) == [D("10.00"), D("6.00")]


def test_fixed_subscription_discount_is_split_by_amount_with_remainder_on_last_line():
    d = discount(type="fixed", value="10", scope="subscriptions")
    ls = lines((P1, 1, "100.00"), (P2, 1, "100.00"), (P3, 1, "100.00"))
    got = amounts(pricing.pick_discounts(ls, [d], SUB, PERIOD))
    assert got == [D("3.33"), D("3.33"), D("3.34")]
    assert sum(got) == D("10.00")

    uneven = amounts(pricing.pick_discounts(lines((P1, 1, "300.00"), (P2, 1, "100.00")), [d], SUB, PERIOD))
    assert uneven == [D("7.50"), D("2.50")]


def test_fixed_subscription_discount_larger_than_the_subtotal_is_capped():
    d = discount(type="fixed", value="1000", scope="subscriptions")
    got = amounts(pricing.pick_discounts(lines((P1, 1, "60.00"), (P2, 1, "40.00")), [d], SUB, PERIOD))
    assert got == [D("60.00"), D("40.00")]


# ------------------------------------------------------------------ one discount per line
def test_one_discount_per_line_and_the_largest_wins():
    small = discount(value="5", products=[P1], name="small")
    big = discount(value="20", products=[P1], name="big")
    sub_wide = discount(value="10", scope="subscriptions", name="wide")
    ls = lines((P1, 1, "100.00"), (P2, 1, "100.00"))
    got = pricing.pick_discounts(ls, [small, big, sub_wide], SUB, PERIOD)
    assert (got[0].name, got[0].amount) == ("big", D("20.00"))  # 20 beats 10 and 5 on the same line
    assert (got[1].name, got[1].amount) == ("wide", D("10.00"))  # only the wide one reaches line 2


def test_tie_goes_to_the_oldest_rule():
    first = discount(value="10", products=[P1], name="first")
    second = discount(value="10", products=[P1], name="second")
    got = pricing.pick_discounts(lines((P1, 1, "100.00")), [first, second], SUB, PERIOD)
    assert got[0].name == "first"


# ------------------------------------------------------------------ totals (rule 7)
def test_tax_is_charged_on_the_discounted_amount_and_totals_add_up():
    d = discount(value="10", products=[P1])
    drafts = [
        InvoiceLineDraft(P1, 2, D("500.00"), "percentage", D("10")),  # gross 1000.00, discount 100.00, tax on 900.00
        InvoiceLineDraft(P2, 1, D("200.00"), "fixed", D("15")),  # no discount, fixed tax per line
    ]
    priced, totals = pricing.price_invoice(drafts, [d], SUB, PERIOD)
    assert [p.discount_amount for p in priced] == [D("100.00"), D("0.00")]
    assert [p.tax_amount for p in priced] == [D("90.00"), D("15.00")]
    assert [p.amount for p in priced] == [D("900.00"), D("200.00")]
    assert totals.subtotal == D("1200.00")
    assert totals.discount_total == D("100.00")
    assert totals.tax_total == D("105.00")
    assert totals.total == D("1205.00")  # subtotal - discount + tax; the plan price is never added


def test_percentage_tax_rounds_half_up_per_line():
    drafts = [InvoiceLineDraft(P1, 1, D("0.05"), "percentage", D("10"))]  # 0.005 -> 0.01
    priced, totals = pricing.price_invoice(drafts, [], SUB, PERIOD)
    assert priced[0].tax_amount == D("0.01")
    assert totals.total == D("0.06")
