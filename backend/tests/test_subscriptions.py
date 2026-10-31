import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import engine
from app.services import periods, pricing
from tests.conftest import TEST_PREFIX, auth_header

API = "/api/v1"
ADMIN = {"email": "admin@brightloop.test", "password": "ChangeMe#2026"}
TODAY = date.today()


def _name(label: str) -> str:
    return f"{TEST_PREFIX}{label}-{uuid.uuid4().hex[:8]}"


def _insert(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar_one()


@pytest.fixture(scope="module")
def admin_headers(client):
    r = client.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return auth_header(r.json()["token"])


@pytest.fixture
def catalogue():
    """Odoo-style product with a +560.00 brand variant, a 10% tax on software and two plans.
    Rows carry the test prefix, so the session cleanup in conftest removes them."""
    with engine.begin() as c:
        tax = _insert(
            c, "insert into taxes (name, computation, value) values (:n, 'percentage', 10) returning id", n=_name("tax")
        )
        c.execute(text("insert into tax_product_types (tax_id, product_type) values (:t, 'software')"), {"t": tax})
        product = _insert(
            c,
            "insert into products (name, type, sales_price, cost_price) values (:n, 'software', 1000, 400) returning id",
            n=_name("odoo"),
        )
        variant = _insert(
            c,
            "insert into product_variants (product_id, attribute, value, extra_price) "
            "values (:p, 'Brand', 'Odoo', 560) returning id",
            p=product,
        )
        flexible = _insert(
            c,
            "insert into plans (name, price, billing_period, min_quantity, available_from, allow_early_close, "
            "allow_pause, allow_renew) values (:n, 100, 'monthly', 2, :f, true, true, true) returning id",
            n=_name("flex"),
            f=TODAY - timedelta(days=30),
        )
        strict = _insert(
            c,
            "insert into plans (name, price, billing_period, available_from, allow_early_close, allow_pause, "
            "allow_renew) values (:n, 100, 'monthly', :f, false, false, false) returning id",
            n=_name("strict"),
            f=TODAY - timedelta(days=30),
        )
    return {"product": str(product), "variant": str(variant), "flexible": str(flexible), "strict": str(strict)}


@pytest.fixture
def customer(new_user):
    _, password, body = new_user("sub")
    return {"id": body["user"]["customerId"], "token": body["token"]}


def _draft(client, headers, customer, plan, product, **overrides):
    payload = {
        "customerId": customer["id"],
        "planId": plan,
        "startDate": str(TODAY),
        "expiryDate": str(TODAY + timedelta(days=365)),
        "paymentTerms": "net_30",
        "lines": [{"productId": product, "quantity": 2}],
        **overrides,
    }
    r = client.post(f"{API}/subscriptions", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _post(client, headers, sub, action, **kw):
    return client.post(f"{API}/subscriptions/{sub['id']}/{action}", headers=headers, **kw)


def _to_active(client, headers, sub):
    for action in ("send-quotation", "confirm", "activate"):
        r = _post(client, headers, sub, action)
        assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ pure pricing
def test_tax_rounds_half_up_per_line():
    class Percent:
        computation, value = "percentage", Decimal("10")

    class Fixed:
        computation, value = "fixed", Decimal("2.50")

    assert pricing.tax_amount(Percent, Decimal("0.05")) == Decimal("0.01")  # 0.005 rounds up, not to even
    assert pricing.tax_amount(Fixed, Decimal("1000.00")) == Decimal("2.50")  # one value per line
    assert pricing.tax_amount(None, Decimal("5")) == Decimal("0.00")


def test_add_period_clamps_month_end():
    assert periods.add_period(date(2026, 1, 31), "monthly") == date(2026, 2, 28)
    assert periods.add_period(date(2026, 3, 1), "yearly") == date(2027, 3, 1)
    assert periods.add_period(date(2026, 3, 1), "weekly") == date(2026, 3, 8)


# ------------------------------------------------------------------ pricing through the API
def test_odoo_variant_adds_560_and_tax_is_applied(client, admin_headers, catalogue, customer):
    sub = _draft(
        client, admin_headers, customer, catalogue["flexible"], catalogue["product"],
        lines=[{"productId": catalogue["product"], "variantId": catalogue["variant"], "quantity": 2}],
    )
    line = sub["lines"][0]
    assert line["unitPrice"] == "1560.00"  # 1000.00 + 560.00 Odoo brand
    assert line["variantLabel"] == "Brand Odoo"
    assert line["amount"] == "3120.00"
    assert line["taxAmount"] == "312.00"  # 10% of 3120.00
    assert (sub["subtotal"], sub["taxTotal"], sub["total"]) == ("3120.00", "312.00", "3432.00")
    assert sub["status"] == "draft" and sub["number"].startswith("SUB-")


def test_unit_price_override(client, admin_headers, catalogue, customer):
    sub = _draft(
        client, admin_headers, customer, catalogue["flexible"], catalogue["product"],
        lines=[{"productId": catalogue["product"], "quantity": 2, "unitPrice": "900.00"}],
    )
    assert sub["lines"][0]["unitPrice"] == "900.00"


# ------------------------------------------------------------------ happy path + history
def test_happy_path_draft_to_active_and_history(client, admin_headers, catalogue, customer):
    sub = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    sent = _post(client, admin_headers, sub, "send-quotation").json()
    assert sent["status"] == "quotation"
    assert sent["quotationValidUntil"] == str(TODAY + timedelta(days=30))
    assert _post(client, admin_headers, sub, "confirm").json()["status"] == "confirmed"
    active = _post(client, admin_headers, sub, "activate").json()
    assert active["status"] == "active"
    assert active["nextBillingDate"] == active["startDate"] == str(TODAY)

    h = client.get(f"{API}/subscriptions/{sub['id']}/history", headers=admin_headers).json()
    assert h["meta"]["total"] == 4
    assert [(e["event"], e["fromStatus"], e["toStatus"]) for e in h["data"]] == [
        ("status_change", "confirmed", "active"),
        ("status_change", "quotation", "confirmed"),
        ("status_change", "draft", "quotation"),
        ("created", None, "draft"),
    ]
    assert h["data"][0]["changedBy"]["name"] == "Admin"


def test_template_fills_plan_lines_and_validity(client, admin_headers, catalogue, customer):
    with engine.begin() as c:
        tpl = _insert(
            c,
            "insert into quotation_templates (name, plan_id, validity_days) values (:n, :p, 10) returning id",
            n=_name("tpl"),
            p=catalogue["flexible"],
        )
        c.execute(
            text("insert into quotation_template_lines (template_id, product_id, quantity) values (:t, :p, 3)"),
            {"t": tpl, "p": catalogue["product"]},
        )
    r = client.post(
        f"{API}/subscriptions", headers=admin_headers, json={"customerId": customer["id"], "templateId": str(tpl)}
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["plan"]["id"] == catalogue["flexible"]
    assert sub["lines"][0]["quantity"] == 3
    assert sub["quotationValidUntil"] == str(TODAY + timedelta(days=10))
    assert sub["templateId"] == str(tpl)


# ------------------------------------------------------------------ errors
def test_wrong_transition_is_409(client, admin_headers, catalogue, customer):
    sub = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    for action in ("confirm", "activate", "close", "pause", "renew"):
        assert _post(client, admin_headers, sub, action).status_code == 409, action
    _to_active(client, admin_headers, sub)
    assert _post(client, admin_headers, sub, "send-quotation").status_code == 409
    r = client.patch(f"{API}/subscriptions/{sub['id']}", json={"notes": "x"}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    assert client.delete(f"{API}/subscriptions/{sub['id']}", headers=admin_headers).status_code == 409


def test_send_quotation_lists_missing_fields(client, admin_headers, customer):
    r = client.post(f"{API}/subscriptions", json={"customerId": customer["id"]}, headers=admin_headers)
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["plan"] is None and sub["startDate"] is None and sub["paymentTerms"] is None
    r = _post(client, admin_headers, sub, "send-quotation")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "BUSINESS_RULE"
    assert {d["field"] for d in err["details"]} == {"planId", "startDate", "expiryDate", "paymentTerms", "lines"}


def test_plan_min_quantity_and_availability_are_422(client, admin_headers, catalogue, customer):
    r = client.post(  # the flexible plan needs a quantity of at least 2
        f"{API}/subscriptions",
        headers=admin_headers,
        json={
            "customerId": customer["id"],
            "planId": catalogue["flexible"],
            "startDate": str(TODAY),
            "lines": [{"productId": catalogue["product"], "quantity": 1}],
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    r = client.post(  # starts before the plan is available
        f"{API}/subscriptions",
        headers=admin_headers,
        json={
            "customerId": customer["id"],
            "planId": catalogue["flexible"],
            "startDate": str(TODAY - timedelta(days=60)),
            "lines": [{"productId": catalogue["product"], "quantity": 2}],
        },
    )
    assert r.status_code == 422


def test_confirm_fails_when_quotation_expired(client, admin_headers, catalogue, customer):
    sub = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    assert _post(client, admin_headers, sub, "send-quotation").status_code == 200
    with engine.begin() as c:
        c.execute(
            text("update subscriptions set quotation_valid_until = current_date - 1 where id = :i"), {"i": sub["id"]}
        )
    r = _post(client, admin_headers, sub, "confirm")
    assert r.status_code == 422 and "expired" in r.json()["error"]["message"]


def test_plan_flags_are_422_not_409(client, admin_headers, catalogue, customer):
    sub = _to_active(
        client, admin_headers, _draft(client, admin_headers, customer, catalogue["strict"], catalogue["product"])
    )
    for action in ("close", "pause", "renew"):
        r = _post(client, admin_headers, sub, action)
        assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE", action


def test_staff_endpoints_reject_customers(client, admin_headers, catalogue, customer):
    sub = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    assert _post(client, auth_header(customer["token"]), sub, "send-quotation").status_code == 403


# ------------------------------------------------------------------ customer scoping
def test_customer_sees_only_own_subscriptions(client, admin_headers, catalogue, customer, new_user):
    mine = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    _, _, other_body = new_user("other")
    other = _draft(
        client, admin_headers, {"id": other_body["user"]["customerId"]}, catalogue["flexible"], catalogue["product"]
    )
    h = auth_header(customer["token"])

    assert client.get(f"{API}/subscriptions/{mine['id']}", headers=h).status_code == 200
    for path in ("", "/history"):
        r = client.get(f"{API}/subscriptions/{other['id']}{path}", headers=h)
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND", path

    listed = client.get(f"{API}/subscriptions", headers=h).json()
    assert [s["id"] for s in listed["data"]] == [mine["id"]]
    assert listed["meta"]["total"] == 1
    # an explicit customerId filter cannot widen a customer's view
    r = client.get(f"{API}/subscriptions", params={"customerId": other["customer"]["id"]}, headers=h).json()
    assert [s["id"] for s in r["data"]] == [mine["id"]]
    # transitions on someone else's subscription are 404 too
    assert client.post(f"{API}/subscriptions/{other['id']}/pause", headers=h).status_code == 404


def test_customer_request_creates_own_draft(client, admin_headers, catalogue, customer):
    body = {
        "planId": catalogue["flexible"],
        "startDate": str(TODAY),
        "lines": [{"productId": catalogue["product"], "variantId": catalogue["variant"], "quantity": 2}],
    }
    r = client.post(f"{API}/subscriptions/request", headers=auth_header(customer["token"]), json=body)
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "draft" and sub["customer"]["id"] == customer["id"]
    assert sub["lines"][0]["unitPrice"] == "1560.00"
    assert sub["expiryDate"] is None and sub["paymentTerms"] is None
    assert client.post(f"{API}/subscriptions/request", headers=admin_headers, json=body).status_code == 403


# ------------------------------------------------------------------ pause / resume / close / renew
def test_pause_resume_next_billing_date(client, admin_headers, catalogue, customer):
    sub = _to_active(
        client,
        admin_headers,
        _draft(
            client, admin_headers, customer, catalogue["flexible"], catalogue["product"],
            startDate=str(TODAY - timedelta(days=20)),
        ),
    )
    assert sub["nextBillingDate"] == str(TODAY - timedelta(days=20))
    cust = auth_header(customer["token"])  # the owning customer may pause: the plan allows it

    assert _post(client, cust, sub, "pause").json()["isPaused"] is True
    assert _post(client, cust, sub, "pause").status_code == 409  # already paused

    resumed = _post(client, cust, sub, "resume").json()
    assert resumed["isPaused"] is False
    assert resumed["nextBillingDate"] == str(TODAY)  # was in the past, so today: no catch-up invoices
    assert _post(client, cust, sub, "resume").status_code == 409  # not paused

    # a future nextBillingDate is never pulled back to today
    future = TODAY + timedelta(days=15)
    with engine.begin() as c:
        c.execute(text("update subscriptions set next_billing_date = :d where id = :i"), {"d": future, "i": sub["id"]})
    _post(client, cust, sub, "pause")
    assert _post(client, cust, sub, "resume").json()["nextBillingDate"] == str(future)

    events = [e["event"] for e in client.get(f"{API}/subscriptions/{sub['id']}/history", headers=cust).json()["data"]]
    assert events[:4] == ["resumed", "paused", "resumed", "paused"]


def test_renew_and_close(client, admin_headers, catalogue, customer):
    sub = _to_active(
        client, admin_headers, _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    )
    old_expiry = date.fromisoformat(sub["expiryDate"])

    renewed = _post(client, admin_headers, sub, "renew").json()
    assert renewed["expiryDate"] == str(periods.add_period(old_expiry, "monthly"))
    assert _post(client, admin_headers, sub, "renew", json={"newExpiryDate": str(old_expiry)}).status_code == 422

    closed = _post(client, admin_headers, sub, "close", json={"reason": "moved away"}).json()
    assert closed["status"] == "closed" and closed["nextBillingDate"] is None
    assert closed["closedAt"] is not None and closed["closeReason"] == "moved away"
    assert _post(client, admin_headers, sub, "renew").status_code == 409  # closed is final

    h = client.get(f"{API}/subscriptions/{sub['id']}/history", headers=admin_headers).json()["data"]
    assert h[0]["toStatus"] == "closed" and h[0]["reason"] == "moved away"
    assert "renewed" in [e["event"] for e in h]


# ------------------------------------------------------------------ edit / delete / list
def test_patch_replaces_lines_and_delete_draft(client, admin_headers, catalogue, customer):
    sub = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    r = client.patch(
        f"{API}/subscriptions/{sub['id']}",
        headers=admin_headers,
        json={
            "lines": [{"productId": catalogue["product"], "variantId": catalogue["variant"], "quantity": 4}],
            "paymentTerms": "net_15",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["lines"]) == 1 and body["lines"][0]["quantity"] == 4 and body["paymentTerms"] == "net_15"
    assert body["subtotal"] == "6240.00"
    assert client.patch(f"{API}/subscriptions/{sub['id']}", json={"planId": None}, headers=admin_headers).status_code == 400

    assert client.delete(f"{API}/subscriptions/{sub['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"{API}/subscriptions/{sub['id']}", headers=admin_headers).status_code == 404


def test_list_filters_and_pagination(client, admin_headers, catalogue, customer):
    a = _draft(client, admin_headers, customer, catalogue["flexible"], catalogue["product"])
    _draft(client, admin_headers, customer, catalogue["strict"], catalogue["product"])
    q = {"customerId": customer["id"]}
    r = client.get(f"{API}/subscriptions", params={**q, "limit": 1}, headers=admin_headers).json()
    assert r["meta"] == {"page": 1, "limit": 1, "total": 2, "totalPages": 2}
    r = client.get(f"{API}/subscriptions", params={**q, "planId": catalogue["flexible"]}, headers=admin_headers).json()
    assert [s["id"] for s in r["data"]] == [a["id"]]
    r = client.get(f"{API}/subscriptions", params={**q, "status": "active"}, headers=admin_headers).json()
    assert r["data"] == []
    assert client.get(f"{API}/subscriptions", params={"limit": 101}, headers=admin_headers).status_code == 400
