"""API.md section 5, end to end: login -> template -> subscription -> activate -> discount -> billing run ->
confirm -> send -> payments -> paid. Catalogue rows (tax, product, plan, template, discount) are inserted with SQL
because their endpoints are not built yet; everything else goes through the HTTP API."""
from datetime import timedelta

from sqlalchemy import text

from app.db import engine
from tests.conftest import TRACKED_RUNS, auth_header
from tests.support import API, TODAY, discount_used_count, make_catalogue, make_customer, make_discount, name


def make_template(cat: dict, quantity: int) -> str:
    with engine.begin() as c:
        template = c.execute(
            text("insert into quotation_templates (name, plan_id, validity_days) values (:n, :p, 30) returning id"),
            {"n": name("template"), "p": cat["plan"]},
        ).scalar_one()
        c.execute(
            text(
                "insert into quotation_template_lines (template_id, product_id, variant_id, quantity) "
                "values (:t, :p, :v, :q)"
            ),
            {"t": template, "p": cat["product"], "v": cat["variant"], "q": quantity},
        )
    return str(template)


def test_the_happy_path_from_login_to_a_paid_invoice(client):
    # 1. login as admin
    r = client.post(f"{API}/auth/login", json={"email": "admin@brightloop.test", "password": "ChangeMe#2026"})
    assert r.status_code == 200, r.text
    admin = auth_header(r.json()["token"])

    # 2. catalogue: 10% tax, product 1000.00 + Odoo variant 560.00, monthly plan, template of 2 units
    cat = make_catalogue()
    template_id = make_template(cat, quantity=2)
    customer = make_customer(client)

    # 3. subscription from the template, then quotation -> confirmed -> active
    r = client.post(
        f"{API}/subscriptions",
        headers=admin,
        json={
            "customerId": customer["id"],
            "templateId": template_id,
            "startDate": str(TODAY),
            "expiryDate": str(TODAY + timedelta(days=365)),
            "paymentTerms": "net_30",
        },
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "draft" and sub["plan"]["id"] == cat["plan"]
    assert [(ln["quantity"], ln["unitPrice"], ln["amount"]) for ln in sub["lines"]] == [(2, "1560.00", "3120.00")]
    assert (sub["subtotal"], sub["taxTotal"], sub["total"]) == ("3120.00", "312.00", "3432.00")
    for step, status in (("send-quotation", "quotation"), ("confirm", "confirmed"), ("activate", "active")):
        r = client.post(f"{API}/subscriptions/{sub['id']}/{step}", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == status
    assert r.json()["nextBillingDate"] == str(TODAY)

    # 4. a 10% discount on the product
    discount_id = make_discount([cat["product"]], value=10)

    # 5. preview, then the real billing run
    due = client.get(f"{API}/billing/due?limit=100", headers=admin).json()["data"]
    assert sub["id"] in {d["subscriptionId"] for d in due}
    dry = client.post(
        f"{API}/billing/run", headers=admin, json={"subscriptionIds": [sub["id"]], "dryRun": True}
    ).json()
    assert dry["counts"]["created"] == 1 and dry["created"][0]["total"] == "3088.80"
    assert discount_used_count(discount_id) == 0  # a dry run spends nothing

    r = client.post(f"{API}/billing/run", headers=admin, json={"subscriptionIds": [sub["id"]]})
    assert r.status_code == 200, r.text
    run = r.json()
    TRACKED_RUNS.add(run["runId"])
    assert run["counts"] == {"due": 1, "created": 1, "alreadyBilled": 0, "failed": 0}
    invoice = run["created"][0]
    # subtotal 3120.00; discount 10% = 312.00; tax 10% of 2808.00 = 280.80; total 3088.80
    assert (invoice["status"], invoice["subtotal"], invoice["discountTotal"], invoice["taxTotal"], invoice["total"]) == (
        "draft", "3120.00", "312.00", "280.80", "3088.80",
    )
    assert discount_used_count(discount_id) == 1

    # rerunning bills nothing again
    again = client.post(f"{API}/billing/run", headers=admin, json={"subscriptionIds": [sub["id"]]}).json()
    TRACKED_RUNS.add(again["runId"])
    assert again["counts"]["created"] == 0
    assert client.get(f"{API}/subscriptions/{sub['id']}/invoices", headers=admin).json()["meta"]["total"] == 1

    # 5b. confirm and send the invoice
    r = client.post(f"{API}/invoices/{invoice['id']}/confirm", headers=admin)
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["issueDate"], r.json()["dueDate"]) == (
        "confirmed", str(TODAY), str(TODAY + timedelta(days=30)),
    )
    r = client.post(f"{API}/invoices/{invoice['id']}/send", headers=admin)
    assert r.status_code == 200 and r.json()["sentAt"] is not None

    # 6. payments: a partial one, then the rest; the invoice becomes paid
    def pay(amount: str):
        return client.post(
            f"{API}/payments",
            headers=admin,
            json={"invoiceId": invoice["id"], "method": "upi", "amount": amount, "paymentDate": str(TODAY)},
        )

    assert pay("1000.00").status_code == 201
    mid = client.get(f"{API}/invoices/{invoice['id']}", headers=admin).json()
    assert (mid["status"], mid["amountPaid"], mid["amountDue"]) == ("confirmed", "1000.00", "2088.80")
    assert pay("2088.81").status_code == 422  # one cent too much
    assert pay("2088.80").status_code == 201
    final = client.get(f"{API}/invoices/{invoice['id']}", headers=admin).json()
    assert (final["status"], final["amountPaid"], final["amountDue"], final["isOverdue"]) == (
        "paid", "3088.80", "0.00", False,
    )
    assert len(final["payments"]) == 2 and final["customerDetails"]["email"] == customer["email"]

    # the customer sees their own paid invoice and its payments
    mine = client.get(f"{API}/invoices", headers=customer["headers"]).json()
    assert [(i["id"], i["status"]) for i in mine["data"]] == [(invoice["id"], "paid")]
    assert client.get(f"{API}/payments", headers=customer["headers"]).json()["meta"]["total"] == 2
    paid_list = client.get(f"{API}/invoices?hasBalance=false&customerId={customer['id']}", headers=admin).json()
    assert [i["id"] for i in paid_list["data"]] == [invoice["id"]]
