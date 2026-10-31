"""Payments (API.md rule 9): only on confirmed invoices, 0 < amount <= amountDue, void moves paid -> confirmed."""
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.db import engine
from tests.support import API, TODAY, make_catalogue, make_customer, make_subscription, run_billing


@pytest.fixture
def cat():
    return make_catalogue()


@pytest.fixture
def customer(client):
    return make_customer(client)


def confirmed_invoice(client, headers, customer, cat) -> str:
    """A confirmed invoice with total 1716.00."""
    sub = make_subscription(client, headers, customer, cat)
    inv_id = run_billing(client, headers, [sub["id"]])["created"][0]["id"]
    r = client.post(f"{API}/invoices/{inv_id}/confirm", headers=headers)
    assert r.status_code == 200, r.text
    return inv_id


def pay(client, headers, invoice_id, amount, **extra):
    body = {"invoiceId": invoice_id, "method": "bank_transfer", "amount": amount, "paymentDate": str(TODAY)} | extra
    return client.post(f"{API}/payments", headers=headers, json=body)


def invoice(client, headers, invoice_id) -> dict:
    return client.get(f"{API}/invoices/{invoice_id}", headers=headers).json()


# ------------------------------------------------------------------ recording
def test_payment_response_shape_and_partial_then_full_payment(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)

    r = pay(client, admin_headers, inv_id, "700.00", reference="TXN-1", note="first part")
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["invoiceId"], p["amount"], p["method"], p["paymentDate"]) == (inv_id, "700.00", "bank_transfer", str(TODAY))
    assert (p["reference"], p["note"], p["isVoided"]) == ("TXN-1", "first part", False)
    assert p["invoiceNumber"].startswith("INV-") and p["customer"]["id"] == customer["id"]
    assert p["recordedBy"] and p["createdAt"]

    inv = invoice(client, admin_headers, inv_id)  # the DB trigger, not the app, moved these
    assert (inv["status"], inv["amountPaid"], inv["amountDue"]) == ("confirmed", "700.00", "1016.00")
    assert [x["id"] for x in inv["payments"]] == [p["id"]]

    assert pay(client, admin_headers, inv_id, "1016.00").status_code == 201
    inv = invoice(client, admin_headers, inv_id)
    assert (inv["status"], inv["amountPaid"], inv["amountDue"], inv["isOverdue"]) == ("paid", "1716.00", "0.00", False)
    assert len(inv["payments"]) == 2

    r = pay(client, admin_headers, inv_id, "1.00")  # nothing left to pay, and the invoice is no longer confirmed
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"


def test_paying_the_whole_amount_at_once_marks_the_invoice_paid(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    assert pay(client, admin_headers, inv_id, "1716.00", method="cash").status_code == 201
    assert invoice(client, admin_headers, inv_id)["status"] == "paid"


def test_overpayment_is_422_and_nothing_is_recorded(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    r = pay(client, admin_headers, inv_id, "1716.01")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BUSINESS_RULE" and r.json()["error"]["details"][0]["field"] == "amount"

    assert pay(client, admin_headers, inv_id, "1000.00").status_code == 201
    assert pay(client, admin_headers, inv_id, "716.01").status_code == 422  # only 716.00 is still due
    inv = invoice(client, admin_headers, inv_id)
    assert (inv["amountPaid"], inv["status"], len(inv["payments"])) == ("1000.00", "confirmed", 1)


@pytest.mark.parametrize("amount", ["0.00", "0", "-5.00"])
def test_zero_and_negative_amounts_are_422(client, admin_headers, cat, customer, amount):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    assert pay(client, admin_headers, inv_id, amount).status_code == 422


def test_other_invalid_input_is_400(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    assert pay(client, admin_headers, inv_id, "10.005").status_code == 400  # more than 2 decimals
    assert pay(client, admin_headers, inv_id, "10.00", method="bitcoin").status_code == 400
    assert pay(client, admin_headers, "00000000-0000-4000-8000-00000000dead", "10.00").status_code == 400
    assert client.post(f"{API}/payments", headers=admin_headers, json={"invoiceId": inv_id}).status_code == 400


def test_only_confirmed_invoices_accept_payments(client, admin_headers, cat, customer):
    sub = make_subscription(client, admin_headers, customer, cat)
    draft = run_billing(client, admin_headers, [sub["id"]])["created"][0]["id"]
    r = pay(client, admin_headers, draft, "10.00")
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"

    client.post(f"{API}/invoices/{draft}/confirm", headers=admin_headers)
    client.post(f"{API}/invoices/{draft}/cancel", headers=admin_headers)
    assert pay(client, admin_headers, draft, "10.00").status_code == 422


def test_customers_cannot_record_or_void_payments(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    assert pay(client, customer["headers"], inv_id, "10.00").status_code == 403
    assert pay(client, {}, inv_id, "10.00").status_code == 401
    payment_id = pay(client, admin_headers, inv_id, "10.00").json()["id"]
    assert client.delete(f"{API}/payments/{payment_id}", headers=customer["headers"]).status_code == 403


# ------------------------------------------------------------------ reading
def test_list_and_get_with_filters_and_customer_scoping(client, admin_headers, cat, customer):
    other = make_customer(client, "other")
    mine = confirmed_invoice(client, admin_headers, customer, cat)
    theirs = confirmed_invoice(client, admin_headers, other, cat)
    p1 = pay(client, admin_headers, mine, "100.00", method="cash").json()
    p2 = pay(client, admin_headers, mine, "200.00", method="card", paymentDate=str(TODAY - timedelta(days=3))).json()
    p3 = pay(client, admin_headers, theirs, "300.00", method="cash").json()

    def listing(query: str, headers=admin_headers):
        r = client.get(f"{API}/payments?{query}", headers=headers)
        assert r.status_code == 200, r.text
        return r.json()

    assert {p["id"] for p in listing(f"invoiceId={mine}")["data"]} == {p1["id"], p2["id"]}
    assert {p["id"] for p in listing(f"customerId={customer['id']}")["data"]} == {p1["id"], p2["id"]}
    assert [p["id"] for p in listing(f"customerId={customer['id']}&method=card")["data"]] == [p2["id"]]
    assert [p["id"] for p in listing(f"invoiceId={mine}&paidFrom={TODAY - timedelta(days=1)}")["data"]] == [p1["id"]]
    assert [p["id"] for p in listing(f"invoiceId={mine}&paidTo={TODAY - timedelta(days=1)}")["data"]] == [p2["id"]]
    assert listing(f"invoiceId={mine}&limit=1")["meta"] == {"page": 1, "limit": 1, "total": 2, "totalPages": 2}

    # a customer sees only payments on their own invoices, even when asking for someone else's
    own = listing("limit=100", customer["headers"])
    assert {p["id"] for p in own["data"]} == {p1["id"], p2["id"]}
    assert listing(f"customerId={other['id']}", customer["headers"])["meta"]["total"] == 2
    assert client.get(f"{API}/payments/{p1['id']}", headers=customer["headers"]).status_code == 200
    assert client.get(f"{API}/payments/{p3['id']}", headers=customer["headers"]).status_code == 404
    assert client.get(f"{API}/payments/{p3['id']}", headers=admin_headers).json()["amount"] == "300.00"
    assert client.get(f"{API}/payments/00000000-0000-4000-8000-00000000dead", headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ voiding
def test_void_marks_the_payment_and_moves_a_paid_invoice_back_to_confirmed(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    first = pay(client, admin_headers, inv_id, "1000.00").json()
    second = pay(client, admin_headers, inv_id, "716.00").json()
    assert invoice(client, admin_headers, inv_id)["status"] == "paid"

    r = client.delete(f"{API}/payments/{second['id']}", headers=admin_headers)
    assert r.status_code == 204 and r.content == b""
    inv = invoice(client, admin_headers, inv_id)
    assert (inv["status"], inv["amountPaid"], inv["amountDue"]) == ("confirmed", "1000.00", "716.00")
    voided = {p["id"]: p for p in inv["payments"]}
    assert voided[second["id"]]["isVoided"] is True and voided[first["id"]]["isVoided"] is False
    assert client.get(f"{API}/payments/{second['id']}", headers=admin_headers).json()["isVoided"] is True

    # voided_at / voided_by were written (the generated is_voided follows); the row is kept for audit
    with engine.connect() as c:
        row = c.execute(
            text("select voided_at is not null, voided_by is not null, is_voided from payments where id = :i"),
            {"i": second["id"]},
        ).one()
    assert tuple(row) == (True, True, True)

    # the freed amount can be paid again, and a second void of the same payment is a conflict
    assert pay(client, admin_headers, inv_id, "716.00").status_code == 201
    assert invoice(client, admin_headers, inv_id)["status"] == "paid"
    assert client.delete(f"{API}/payments/{second['id']}", headers=admin_headers).status_code == 409
    assert client.delete(f"{API}/payments/00000000-0000-4000-8000-00000000dead", headers=admin_headers).status_code == 404


def test_invoice_with_payments_cannot_be_cancelled_until_they_are_voided(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    payment_id = pay(client, admin_headers, inv_id, "10.00").json()["id"]

    r = client.post(f"{API}/invoices/{inv_id}/cancel", headers=admin_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert invoice(client, admin_headers, inv_id)["status"] == "confirmed"

    assert client.delete(f"{API}/payments/{payment_id}", headers=admin_headers).status_code == 204
    assert client.post(f"{API}/invoices/{inv_id}/cancel", headers=admin_headers).json()["status"] == "cancelled"


# ------------------------------------------------------------------ PR #4 review by Prakash
def test_a_future_payment_date_is_422(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    r = pay(client, admin_headers, inv_id, "10.00", paymentDate=str(TODAY + timedelta(days=1)))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BUSINESS_RULE" and r.json()["error"]["details"][0]["field"] == "paymentDate"
    assert invoice(client, admin_headers, inv_id)["payments"] == []
    # today and the past are fine
    assert pay(client, admin_headers, inv_id, "10.00", paymentDate=str(TODAY)).status_code == 201
    assert pay(client, admin_headers, inv_id, "10.00", paymentDate=str(TODAY - timedelta(days=30))).status_code == 201


def test_the_balance_check_uses_amount_due_from_the_view(client, admin_headers, cat, customer):
    inv_id = confirmed_invoice(client, admin_headers, customer, cat)
    assert pay(client, admin_headers, inv_id, "1700.00").status_code == 201
    over = pay(client, admin_headers, inv_id, "16.01")
    assert over.status_code == 422 and "16.00" in over.json()["error"]["message"]
    assert pay(client, admin_headers, inv_id, "16.00").status_code == 201
    assert invoice(client, admin_headers, inv_id)["status"] == "paid"
