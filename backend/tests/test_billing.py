"""Billing run, due preview, run history and discounts on generated invoices (API.md section 3, rules 6-8)."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.services import billing_service
from app.services.periods import add_months
from tests.support import (
    API,
    TODAY,
    discount_used_count,
    invoices_of,
    make_catalogue,
    make_customer,
    make_discount,
    make_subscription,
    next_billing_date,
    periods_until,
    run_billing,
    set_subscription,
)

D = Decimal


@pytest.fixture
def cat():
    return make_catalogue()


@pytest.fixture
def customer(client):
    return make_customer(client)


# ------------------------------------------------------------------ the run
def test_run_creates_a_draft_invoice_and_advances_the_billing_date(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    assert sub["nextBillingDate"] == str(TODAY)

    result = run_billing(client, admin_headers, [sub["id"]])
    assert result["dryRun"] is False
    assert result["counts"] == {"due": 1, "created": 1, "alreadyBilled": 0, "failed": 0}
    inv = result["created"][0]
    assert inv["status"] == "draft"
    assert inv["subscriptionId"] == sub["id"]
    assert inv["customer"]["id"] == customer["id"]
    # 1000.00 + 560.00 variant; 10% tax; the plan's list price (100) is never added
    assert (inv["subtotal"], inv["discountTotal"], inv["taxTotal"], inv["total"]) == (
        "1560.00", "0.00", "156.00", "1716.00",
    )
    assert (inv["amountPaid"], inv["amountDue"], inv["isOverdue"]) == ("0.00", "1716.00", False)
    assert inv["periodStart"] == str(TODAY)
    assert inv["periodEnd"] == str(add_months(TODAY, 1) - timedelta(days=1))
    assert inv["issueDate"] is None and inv["dueDate"] is None
    assert next_billing_date(client, admin_headers, sub["id"]) == str(add_months(TODAY, 1))


def test_invoice_lines_are_snapshots_of_the_subscription_lines(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat, quantity=2)
    inv_id = run_billing(client, admin_headers, [sub["id"]])["created"][0]["id"]
    inv = client.get(f"{API}/invoices/{inv_id}", headers=admin_headers).json()
    [line] = inv["lines"]
    assert line["productId"] == cat["product"]
    assert "Brand Odoo" in line["description"]
    assert (line["quantity"], line["unitPrice"], line["amount"], line["taxAmount"]) == (2, "1560.00", "3120.00", "312.00")
    assert line["taxName"] and line["taxRate"] == 10.0
    assert inv["customerDetails"]["name"] == "Billing Customer"
    assert inv["customerDetails"]["email"] == customer["email"]


def test_rerun_creates_no_duplicates(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    run_billing(client, admin_headers, [sub["id"]])

    again = run_billing(client, admin_headers, [sub["id"]])
    assert again["counts"] == {"due": 0, "created": 0, "alreadyBilled": 0, "failed": 0}
    assert len(invoices_of(client, admin_headers, sub["id"])) == 1


def test_already_billed_period_is_counted_not_failed_and_the_date_moves_on(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    run_billing(client, admin_headers, [sub["id"]])
    set_subscription(sub["id"], next_billing_date=TODAY)  # drift: the period already has a live invoice

    result = run_billing(client, admin_headers, [sub["id"]])
    assert result["counts"] == {"due": 1, "created": 0, "alreadyBilled": 1, "failed": 0}
    assert len(invoices_of(client, admin_headers, sub["id"])) == 1
    assert next_billing_date(client, admin_headers, sub["id"]) == str(add_months(TODAY, 1))


def test_missed_periods_are_caught_up_one_invoice_per_period(client, admin_headers, cat, customer):
    start = add_months(TODAY, -3)
    expiry = TODAY + timedelta(days=400)
    sub = make_subscription(client, admin_headers, customer, cat, start=start, expiry=expiry)

    result = run_billing(client, admin_headers, [sub["id"]])
    expected = periods_until(start, TODAY, expiry)
    assert len(expected) >= 4
    assert result["counts"]["created"] == len(expected)
    assert sorted(i["periodStart"] for i in result["created"]) == [str(d) for d in expected]
    assert len({i["number"] for i in result["created"]}) == len(expected)
    assert next_billing_date(client, admin_headers, sub["id"]) == str(add_months(expected[-1], 1))
    assert run_billing(client, admin_headers, [sub["id"]])["counts"]["created"] == 0


def test_no_period_starts_after_expiry(client, admin_headers, cat, customer):
    start = add_months(TODAY, -3)
    expiry = start + timedelta(days=45)  # periods start at +0 and +1 month; the third would start after expiry
    sub = make_subscription(client, admin_headers, customer, cat, start=start, expiry=expiry)

    result = run_billing(client, admin_headers, [sub["id"]])
    assert result["counts"]["created"] == len(periods_until(start, TODAY, expiry)) == 2
    assert max(i["periodStart"] for i in result["created"]) <= str(expiry)
    # the date moved past expiry, so the subscription is no longer a candidate
    assert run_billing(client, admin_headers, [sub["id"]])["counts"]["due"] == 0


def test_not_candidates_future_paused_and_closed(client, admin_headers, cat, customer):
    future = make_subscription(client, admin_headers, customer, cat, start=TODAY + timedelta(days=10))
    paused = make_subscription(client, admin_headers, customer, cat)
    closed = make_subscription(client, admin_headers, customer, cat)
    assert client.post(f"{API}/subscriptions/{paused['id']}/pause", headers=admin_headers).status_code == 200
    assert client.post(f"{API}/subscriptions/{closed['id']}/close", headers=admin_headers, json={}).status_code == 200

    result = run_billing(client, admin_headers, [future["id"], paused["id"], closed["id"]])
    assert result["counts"] == {"due": 0, "created": 0, "alreadyBilled": 0, "failed": 0}
    # asOf in the future makes the not-yet-started subscription due
    later = run_billing(client, admin_headers, [future["id"]], as_of=TODAY + timedelta(days=10))
    assert later["counts"]["created"] == 1


# ------------------------------------------------------------------ dry run and history
def test_dry_run_reports_but_saves_nothing(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    result = run_billing(client, admin_headers, [sub["id"]], dry_run=True)
    assert result["dryRun"] is True
    assert result["counts"]["created"] == 1
    assert result["created"][0]["total"] == "1716.00"

    assert invoices_of(client, admin_headers, sub["id"]) == []
    assert next_billing_date(client, admin_headers, sub["id"]) == str(TODAY)
    assert client.get(f"{API}/billing/runs/{result['runId']}", headers=admin_headers).status_code == 404
    runs = client.get(f"{API}/billing/runs?limit=100", headers=admin_headers).json()["data"]
    assert result["runId"] not in {r["runId"] for r in runs}
    # and a real run afterwards still bills the period
    assert run_billing(client, admin_headers, [sub["id"]])["counts"]["created"] == 1


def test_real_runs_are_stored_and_readable(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    result = run_billing(client, admin_headers, [sub["id"]])

    runs = client.get(f"{API}/billing/runs?limit=100", headers=admin_headers).json()
    assert runs["meta"]["total"] >= 1
    mine = next(r for r in runs["data"] if r["runId"] == result["runId"])
    assert mine["counts"] == result["counts"] and mine["asOf"] == str(TODAY)
    assert mine["startedBy"] is not None

    detail = client.get(f"{API}/billing/runs/{result['runId']}", headers=admin_headers).json()
    assert detail["counts"] == result["counts"]
    assert [i["id"] for i in detail["created"]] == [i["id"] for i in result["created"]]
    assert detail["failed"] == []
    assert client.get(f"{API}/billing/runs/00000000-0000-4000-8000-00000000dead", headers=admin_headers).status_code == 404


def test_one_failing_subscription_does_not_block_the_others(client, admin_headers, cat, customer, monkeypatch):
    bad = make_subscription(client, admin_headers, customer, cat)
    good = make_subscription(client, admin_headers, customer, cat)
    real = billing_service._create_invoice

    def flaky(db, sub, *args, **kwargs):
        if str(sub.id) == bad["id"]:
            raise RuntimeError("boom")
        return real(db, sub, *args, **kwargs)

    monkeypatch.setattr(billing_service, "_create_invoice", flaky)
    result = run_billing(client, admin_headers, [bad["id"], good["id"]])

    assert result["counts"] == {"due": 2, "created": 1, "alreadyBilled": 0, "failed": 1}
    assert [f["subscriptionId"] for f in result["failed"]] == [bad["id"]]
    assert result["failed"][0]["number"] == bad["number"] and "boom" in result["failed"][0]["reason"]
    # the failed subscription was rolled back entirely, so it can simply be retried
    assert next_billing_date(client, admin_headers, bad["id"]) == str(TODAY)
    assert invoices_of(client, admin_headers, bad["id"]) == []
    assert len(invoices_of(client, admin_headers, good["id"])) == 1
    # failures are stored with the run
    detail = client.get(f"{API}/billing/runs/{result['runId']}", headers=admin_headers).json()
    assert detail["counts"]["failed"] == 1 and detail["failed"][0]["subscriptionId"] == bad["id"]


def test_due_preview(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    r = client.get(f"{API}/billing/due?limit=100", headers=admin_headers)
    assert r.status_code == 200
    mine = next(d for d in r.json()["data"] if d["subscriptionId"] == sub["id"])
    assert mine["number"] == sub["number"]
    assert (mine["nextBillingDate"], mine["estimatedTotal"]) == (str(TODAY), "1716.00")
    assert mine["customer"]["id"] == customer["id"]

    before = client.get(f"{API}/billing/due?asOf={TODAY - timedelta(days=1)}&limit=100", headers=admin_headers).json()
    assert sub["id"] not in {d["subscriptionId"] for d in before["data"]}

    run_billing(client, admin_headers, [sub["id"]])
    after = client.get(f"{API}/billing/due?limit=100", headers=admin_headers).json()
    assert sub["id"] not in {d["subscriptionId"] for d in after["data"]}


def test_billing_is_staff_only(client, customer, admin_headers):
    for method, path in (("get", "/billing/due"), ("post", "/billing/run"), ("get", "/billing/runs")):
        assert getattr(client, method)(f"{API}{path}", headers=customer["headers"]).status_code == 403
        assert getattr(client, method)(f"{API}{path}").status_code == 401


# ------------------------------------------------------------------ discounts on invoices (rule 6)
def test_product_discount_is_applied_and_tax_is_charged_on_the_discounted_amount(client, admin_headers, cat, customer):
    did = make_discount([cat["product"]], value=10)
    sub = make_subscription(client, admin_headers, customer, cat)
    inv = run_billing(client, admin_headers, [sub["id"]])["created"][0]

    # 10% of 1560.00 = 156.00; tax 10% of 1404.00 = 140.40; total = 1560.00 - 156.00 + 140.40
    assert (inv["subtotal"], inv["discountTotal"], inv["taxTotal"], inv["total"]) == (
        "1560.00", "156.00", "140.40", "1544.40",
    )
    full = client.get(f"{API}/invoices/{inv['id']}", headers=admin_headers).json()
    [line] = full["lines"]
    assert (line["discountId"], line["discountAmount"], line["amount"], line["taxAmount"]) == (
        did, "156.00", "1404.00", "140.40",
    )
    assert discount_used_count(did) == 1


def test_largest_discount_wins_per_line(client, admin_headers, cat, customer):
    small = make_discount([cat["product"]], value=5)
    big = make_discount([cat["product"]], type="fixed", value=300)
    sub = make_subscription(client, admin_headers, customer, cat)
    inv = run_billing(client, admin_headers, [sub["id"]])["created"][0]

    assert inv["discountTotal"] == "300.00"
    line = client.get(f"{API}/invoices/{inv['id']}", headers=admin_headers).json()["lines"][0]
    assert line["discountId"] == big
    assert (discount_used_count(big), discount_used_count(small)) == (1, 0)


def test_usage_limit_stops_a_discount_once_it_is_used_up(client, admin_headers, cat, customer):
    did = make_discount([cat["product"]], value=10, usage_limit=1)
    first = make_subscription(client, admin_headers, customer, cat)
    second = make_subscription(client, admin_headers, customer, cat)

    result = run_billing(client, admin_headers, [first["id"], second["id"]])
    assert result["counts"]["created"] == 2 and result["counts"]["failed"] == 0
    assert sorted(i["discountTotal"] for i in result["created"]) == ["0.00", "156.00"]
    assert discount_used_count(did) == 1

    # later periods do not get it either
    again = run_billing(client, admin_headers, [first["id"], second["id"]], as_of=add_months(TODAY, 1))
    assert again["counts"]["created"] == 2
    assert {i["discountTotal"] for i in again["created"]} == {"0.00"}
    assert discount_used_count(did) == 1


def test_discount_outside_its_dates_or_under_its_minimums_is_not_applied(client, admin_headers, cat, customer):
    make_discount([cat["product"]], end_date=TODAY - timedelta(days=1))  # expired
    make_discount([cat["product"]], start_date=TODAY + timedelta(days=5))  # not started
    make_discount([cat["product"]], min_quantity=3)  # quantity 1 is under the minimum
    make_discount(scope="subscriptions", min_purchase_amount=5000)  # subtotal 1560.00 is under the minimum
    sub = make_subscription(client, admin_headers, customer, cat)
    inv = run_billing(client, admin_headers, [sub["id"]])["created"][0]
    assert (inv["discountTotal"], inv["total"]) == ("0.00", "1716.00")


def test_subscription_scope_discount_targets_listed_subscriptions_only(client, admin_headers, cat, customer):
    listed = make_subscription(client, admin_headers, customer, cat)
    other = make_subscription(client, admin_headers, customer, cat)
    make_discount(scope="subscriptions", type="fixed", value=100, subscription_ids=[listed["id"]])

    result = run_billing(client, admin_headers, [listed["id"], other["id"]])
    by_sub = {i["subscriptionId"]: i for i in result["created"]}
    assert by_sub[listed["id"]]["discountTotal"] == "100.00"
    assert by_sub[other["id"]]["discountTotal"] == "0.00"
