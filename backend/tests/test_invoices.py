"""Invoice reads, filters, scoping, draft correction, confirm, cancel and send (API.md sections 2 and 3)."""
import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import engine
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
    run_billing,
)

D = Decimal


@pytest.fixture
def cat():
    return make_catalogue()


@pytest.fixture
def customer(client):
    return make_customer(client)


def billed(client, headers, customer, cat, **kwargs):
    """(subscription, first draft invoice id)."""
    sub = make_subscription(client, headers, customer, cat, **kwargs)
    return sub, run_billing(client, headers, [sub["id"]])["created"][0]["id"]


def post(client, headers, path, **kwargs):
    return client.post(f"{API}{path}", headers=headers, **kwargs)


def get_invoice(client, headers, invoice_id):
    r = client.get(f"{API}/invoices/{invoice_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def sql(statement: str, **params):
    with engine.begin() as c:
        c.execute(text(statement), params)


# ------------------------------------------------------------------ reads and scoping
def test_get_invoice_returns_lines_payments_and_customer_details(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat)
    inv = get_invoice(client, admin_headers, inv_id)
    assert inv["number"].startswith("INV-") and inv["status"] == "draft"
    assert len(inv["lines"]) == 1 and inv["payments"] == []
    assert inv["customerDetails"]["name"] == "Billing Customer"
    assert inv["customerDetails"]["email"] == customer["email"]
    assert inv["subscriptionNumber"].startswith("SUB-")
    assert inv["total"] == "1716.00" and inv["amountDue"] == "1716.00"


def test_customer_details_are_a_snapshot_and_do_not_follow_later_customer_edits(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat)
    sql("update customers set name = :n, city = 'Elsewhere' where id = :id", n="pytest-renamed", id=customer["id"])
    inv = get_invoice(client, admin_headers, inv_id)
    assert inv["customerDetails"]["name"] == "Billing Customer"  # as copied at creation
    assert inv["customer"]["name"] == "pytest-renamed"  # the live customer reference


def test_customer_sees_only_own_invoices_and_others_are_404(client, admin_headers, cat, customer):
    other = make_customer(client, "other")
    _, mine = billed(client, admin_headers, customer, cat)
    _, theirs = billed(client, admin_headers, other, cat)
    for inv_id in (mine, theirs):  # customers never see drafts, so issue them first
        assert post(client, admin_headers, f"/invoices/{inv_id}/confirm").status_code == 200

    assert get_invoice(client, customer["headers"], mine)["id"] == mine
    assert client.get(f"{API}/invoices/{theirs}", headers=customer["headers"]).status_code == 404
    listed = client.get(f"{API}/invoices", headers=customer["headers"]).json()
    assert [i["id"] for i in listed["data"]] == [mine]
    # a customer cannot widen the list with customerId, nor read someone else's subscription invoices
    widened = client.get(f"{API}/invoices?customerId={other['id']}", headers=customer["headers"]).json()
    assert [i["id"] for i in widened["data"]] == [mine]
    other_sub = client.get(f"{API}/invoices/{theirs}", headers=admin_headers).json()["subscriptionId"]
    assert client.get(f"{API}/subscriptions/{other_sub}/invoices", headers=customer["headers"]).status_code == 404
    # customers cannot change invoices
    assert post(client, customer["headers"], f"/invoices/{mine}/confirm").status_code == 403


def test_customers_never_see_draft_invoices_but_staff_do(client, admin_headers, cat, customer):
    sub, draft = billed(client, admin_headers, customer, cat)
    own = customer["headers"]

    assert client.get(f"{API}/invoices/{draft}", headers=own).status_code == 404
    assert client.get(f"{API}/invoices", headers=own).json()["data"] == []
    assert client.get(f"{API}/invoices?status=draft", headers=own).json()["meta"]["total"] == 0
    assert client.get(f"{API}/subscriptions/{sub['id']}/invoices", headers=own).json()["data"] == []
    # staff and admin still see it
    assert get_invoice(client, admin_headers, draft)["status"] == "draft"
    assert [i["id"] for i in invoices_of(client, admin_headers, sub["id"])] == [draft]

    # once confirmed it appears for the customer everywhere
    post(client, admin_headers, f"/invoices/{draft}/confirm")
    assert get_invoice(client, own, draft)["status"] == "confirmed"
    assert [i["id"] for i in client.get(f"{API}/invoices", headers=own).json()["data"]] == [draft]
    assert [i["id"] for i in client.get(f"{API}/subscriptions/{sub['id']}/invoices", headers=own).json()["data"]] == [draft]


def test_list_filters_and_pagination(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat, start=add_months(TODAY, -2))
    run_billing(client, admin_headers, [sub["id"]])  # three draft invoices
    ids = [i["id"] for i in invoices_of(client, admin_headers, sub["id"])]
    assert len(ids) == 3
    assert post(client, admin_headers, f"/invoices/{ids[0]}/confirm").status_code == 200

    def listing(query: str):
        r = client.get(f"{API}/invoices?customerId={customer['id']}&{query}", headers=admin_headers)
        assert r.status_code == 200, r.text
        return r.json()

    assert listing("limit=2")["meta"] == {"page": 1, "limit": 2, "total": 3, "totalPages": 2}
    assert len(listing("limit=2&page=2")["data"]) == 1
    assert client.get(f"{API}/invoices?limit=101", headers=admin_headers).status_code == 400
    assert listing("status=draft")["meta"]["total"] == 2
    assert [i["id"] for i in listing("status=confirmed")["data"]] == [ids[0]]
    assert listing(f"subscriptionId={sub['id']}")["meta"]["total"] == 3
    assert listing(f"q={sub['number']}")["meta"]["total"] == 3
    assert listing("q=no-such-invoice")["meta"]["total"] == 0
    assert listing(f"issuedFrom={TODAY}&issuedTo={TODAY}")["meta"]["total"] == 1
    assert listing(f"issuedFrom={TODAY + timedelta(days=1)}")["meta"]["total"] == 0
    assert listing("hasBalance=true")["meta"]["total"] == 3
    assert listing("hasBalance=false")["meta"]["total"] == 0
    assert listing("isOverdue=true")["meta"]["total"] == 0


def test_is_overdue_comes_from_the_view(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat, terms="immediate")
    post(client, admin_headers, f"/invoices/{inv_id}/confirm")
    assert get_invoice(client, admin_headers, inv_id)["isOverdue"] is False  # due today is not overdue yet

    sql("update invoices set issue_date = :i, due_date = :d where id = :id",
        i=TODAY - timedelta(days=40), d=TODAY - timedelta(days=10), id=inv_id)
    inv = get_invoice(client, admin_headers, inv_id)
    assert inv["isOverdue"] is True and inv["amountDue"] == "1716.00"
    overdue = client.get(f"{API}/invoices?isOverdue=true&customerId={customer['id']}", headers=admin_headers).json()
    assert [i["id"] for i in overdue["data"]] == [inv_id]
    not_overdue = client.get(f"{API}/invoices?isOverdue=false&customerId={customer['id']}", headers=admin_headers).json()
    assert not_overdue["data"] == []


# ------------------------------------------------------------------ PATCH (draft only)
def test_patch_recomputes_discount_tax_and_totals(client, admin_headers, cat, customer):
    did = make_discount([cat["product"]], value=10)
    _, inv_id = billed(client, admin_headers, customer, cat)
    inv = get_invoice(client, admin_headers, inv_id)
    assert inv["total"] == "1544.40" and discount_used_count(did) == 1
    line_id = inv["lines"][0]["id"]

    r = client.patch(
        f"{API}/invoices/{inv_id}",
        headers=admin_headers,
        json={"notes": "corrected", "lines": [{"id": line_id, "quantity": 3, "unitPrice": "100.00", "description": "Custom"}]},
    )
    assert r.status_code == 200, r.text
    inv = r.json()
    [line] = inv["lines"]
    # 3 x 100.00 = 300.00; 10% discount 30.00; tax 10% of 270.00 = 27.00; total 297.00
    assert (line["description"], line["quantity"], line["unitPrice"]) == ("Custom", 3, "100.00")
    assert (line["discountAmount"], line["amount"], line["taxAmount"]) == ("30.00", "270.00", "27.00")
    assert (inv["subtotal"], inv["discountTotal"], inv["taxTotal"], inv["total"]) == ("300.00", "30.00", "27.00", "297.00")
    assert inv["notes"] == "corrected"
    assert discount_used_count(did) == 1  # still one usage: re-pricing the same invoice does not spend another


def test_patch_that_drops_a_discount_releases_its_usage(client, admin_headers, cat, customer):
    did = make_discount([cat["product"]], value=10, min_purchase_amount=1000)
    _, inv_id = billed(client, admin_headers, customer, cat)
    inv = get_invoice(client, admin_headers, inv_id)
    assert discount_used_count(did) == 1

    r = client.patch(
        f"{API}/invoices/{inv_id}", headers=admin_headers, json={"lines": [{"id": inv["lines"][0]["id"], "unitPrice": "10.00"}]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["discountTotal"] == "0.00"  # 10.00 is under the discount's minimum purchase amount
    assert discount_used_count(did) == 0
    # restoring the price brings the discount (and the usage) back
    r = client.patch(
        f"{API}/invoices/{inv_id}", headers=admin_headers, json={"lines": [{"id": inv["lines"][0]["id"], "unitPrice": "1560.00"}]}
    )
    assert r.json()["discountTotal"] == "156.00" and discount_used_count(did) == 1


def test_patch_rules(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat)
    inv = get_invoice(client, admin_headers, inv_id)
    line_id = inv["lines"][0]["id"]

    foreign = "00000000-0000-4000-8000-00000000dead"
    r = client.patch(f"{API}/invoices/{inv_id}", headers=admin_headers, json={"lines": [{"id": foreign, "quantity": 2}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.patch(f"{API}/invoices/{inv_id}", headers=admin_headers, json={"lines": [{"id": line_id, "quantity": 0}]})
    assert r.status_code == 400

    assert post(client, admin_headers, f"/invoices/{inv_id}/confirm").status_code == 200
    r = client.patch(f"{API}/invoices/{inv_id}", headers=admin_headers, json={"notes": "too late"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


# ------------------------------------------------------------------ confirm
@pytest.mark.parametrize("terms, days", [("immediate", 0), ("net_15", 15), ("net_30", 30), ("net_60", 60)])
def test_confirm_sets_issue_and_due_dates_from_payment_terms(client, admin_headers, cat, customer, terms, days):
    _, inv_id = billed(client, admin_headers, customer, cat, terms=terms)
    r = post(client, admin_headers, f"/invoices/{inv_id}/confirm")
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["status"] == "confirmed"
    assert inv["issueDate"] == str(TODAY)
    assert inv["dueDate"] == str(TODAY + timedelta(days=days))


def test_confirm_twice_is_409(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat)
    assert post(client, admin_headers, f"/invoices/{inv_id}/confirm").status_code == 200
    r = post(client, admin_headers, f"/invoices/{inv_id}/confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    assert post(client, admin_headers, "/invoices/00000000-0000-4000-8000-00000000dead/confirm").status_code == 404


# ------------------------------------------------------------------ cancel
def test_cancel_releases_the_discount_and_rewinds_the_billing_date_so_the_period_is_billed_again(client, admin_headers, cat, customer):
    did = make_discount([cat["product"]], value=10, usage_limit=1)
    sub, inv_id = billed(client, admin_headers, customer, cat)
    assert discount_used_count(did) == 1
    assert next_billing_date(client, admin_headers, sub["id"]) == str(add_months(TODAY, 1))

    r = post(client, admin_headers, f"/invoices/{inv_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert discount_used_count(did) == 0  # usage given back
    assert next_billing_date(client, admin_headers, sub["id"]) == str(TODAY)  # rewound to periodStart

    again = run_billing(client, admin_headers, [sub["id"]])
    assert again["counts"]["created"] == 1
    new = again["created"][0]
    assert new["id"] != inv_id and new["periodStart"] == str(TODAY)
    assert new["discountTotal"] == "156.00"  # the released usage is spendable again
    assert discount_used_count(did) == 1


def test_cancelling_an_older_invoice_does_not_rewind(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat, start=add_months(TODAY, -1))
    run_billing(client, admin_headers, [sub["id"]])
    invoices = sorted(invoices_of(client, admin_headers, sub["id"]), key=lambda i: i["periodStart"])
    assert len(invoices) == 2
    before = next_billing_date(client, admin_headers, sub["id"])

    assert post(client, admin_headers, f"/invoices/{invoices[0]['id']}/cancel").status_code == 200
    assert next_billing_date(client, admin_headers, sub["id"]) == before

    # the latest one does rewind
    assert post(client, admin_headers, f"/invoices/{invoices[1]['id']}/cancel").status_code == 200
    assert next_billing_date(client, admin_headers, sub["id"]) == invoices[1]["periodStart"]


def test_cancel_a_confirmed_invoice_and_cancel_twice(client, admin_headers, cat, customer):
    _, inv_id = billed(client, admin_headers, customer, cat)
    post(client, admin_headers, f"/invoices/{inv_id}/confirm")
    assert post(client, admin_headers, f"/invoices/{inv_id}/cancel").json()["status"] == "cancelled"
    assert post(client, admin_headers, f"/invoices/{inv_id}/cancel").status_code == 409
    assert post(client, admin_headers, f"/invoices/{inv_id}/confirm").status_code == 409


# ------------------------------------------------------------------ send
def test_send_needs_a_confirmed_invoice_logs_the_email_and_sets_sent_at(client, admin_headers, cat, customer, caplog):
    _, inv_id = billed(client, admin_headers, customer, cat)
    assert post(client, admin_headers, f"/invoices/{inv_id}/send").status_code == 409  # still a draft
    post(client, admin_headers, f"/invoices/{inv_id}/confirm")

    with caplog.at_level(logging.INFO, logger="app.invoices"):
        r = post(client, admin_headers, f"/invoices/{inv_id}/send")
    assert r.status_code == 200, r.text
    assert r.json()["sentAt"] is not None
    assert any(customer["email"] in rec.getMessage() for rec in caplog.records)

    with caplog.at_level(logging.INFO, logger="app.invoices"):
        r = post(client, admin_headers, f"/invoices/{inv_id}/send", json={"to": "billing@example.com", "message": "Thanks"})
    assert r.status_code == 200
    assert any("billing@example.com" in rec.getMessage() for rec in caplog.records)
    assert post(client, admin_headers, f"/invoices/{inv_id}/send", json={"to": "not-an-email"}).status_code == 400
