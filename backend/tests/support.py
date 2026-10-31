"""Builders shared by the billing, invoice and payment tests.

The catalogue and discount endpoints are not part of this API yet, so catalogue rows are inserted with SQL (every
row carries TEST_PREFIX in its name, so conftest cleans it up). Everything from the customer onwards goes
through the real HTTP API, exactly like API.md section 5.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.db import engine
from app.services.periods import add_period
from tests.conftest import TEST_PREFIX, TRACKED_RUNS, auth_header, unique_email

API = "/api/v1"
TODAY = date.today()
D = Decimal

# product 1000.00 + variant 560.00 = 1560.00 per unit; 10% tax on software.
UNIT_PRICE = D("1560.00")
TAX_RATE = D("10")


def name(label: str) -> str:
    return f"{TEST_PREFIX}{label}-{uuid.uuid4().hex[:8]}"


def _insert(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar_one()


def make_catalogue(billing_period: str = "monthly", **plan_flags) -> dict:
    """tax (10% on software) + product with a +560.00 variant + a plan. Plan flags default to everything allowed."""
    flags = {"auto_close": False, "allow_early_close": True, "allow_pause": True, "allow_renew": True} | plan_flags
    with engine.begin() as c:
        tax = _insert(
            c, "insert into taxes (name, computation, value) values (:n, 'percentage', 10) returning id", n=name("tax")
        )
        c.execute(text("insert into tax_product_types (tax_id, product_type) values (:t, 'software')"), {"t": tax})
        product = _insert(
            c,
            "insert into products (name, type, sales_price, cost_price) values (:n, 'software', 1000, 400) returning id",
            n=name("odoo"),
        )
        variant = _insert(
            c,
            "insert into product_variants (product_id, attribute, value, extra_price) "
            "values (:p, 'Brand', 'Odoo', 560) returning id",
            p=product,
        )
        plan = _insert(
            c,
            "insert into plans (name, price, billing_period, min_quantity, available_from, auto_close, "
            "allow_early_close, allow_pause, allow_renew) "
            "values (:n, 100, :bp, 1, :f, :ac, :aec, :ap, :ar) returning id",
            n=name("plan"),
            bp=billing_period,
            f=TODAY - timedelta(days=800),
            ac=flags["auto_close"],
            aec=flags["allow_early_close"],
            ap=flags["allow_pause"],
            ar=flags["allow_renew"],
        )
    return {"product": str(product), "variant": str(variant), "plan": str(plan), "billing_period": billing_period}


def make_discount(
    products: list[str] | None = None,
    *,
    type: str = "percentage",
    value: int | str = 10,
    scope: str = "products",
    usage_limit: int | None = None,
    min_quantity: int | None = None,
    min_purchase_amount: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    subscription_ids: list[str] | None = None,
) -> str:
    with engine.begin() as c:
        did = _insert(
            c,
            "insert into discounts (name, type, value, scope, usage_limit, min_quantity, min_purchase_amount, "
            "start_date, end_date) values (:n, :t, :v, :s, :ul, :mq, :mp, :sd, :ed) returning id",
            n=name("disc"),
            t=type,
            v=value,
            s=scope,
            ul=usage_limit,
            mq=min_quantity,
            mp=min_purchase_amount,
            sd=start_date or TODAY - timedelta(days=800),
            ed=end_date,
        )
        for p in products or []:
            c.execute(text("insert into discount_products (discount_id, product_id) values (:d, :p)"), {"d": did, "p": p})
        for s in subscription_ids or []:
            c.execute(
                text("insert into discount_subscriptions (discount_id, subscription_id) values (:d, :s)"),
                {"d": did, "s": s},
            )
    return str(did)


def discount_used_count(discount_id: str) -> int:
    with engine.connect() as c:
        return c.execute(text("select used_count from discounts where id = :d"), {"d": discount_id}).scalar_one()


def make_customer(client, label: str = "cust") -> dict:
    email = unique_email(label)
    r = client.post(
        f"{API}/auth/signup", json={"name": "Billing Customer", "email": email, "password": "Sup3r#Secret"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return {"id": body["user"]["customerId"], "token": body["token"], "headers": auth_header(body["token"]), "email": email}


def make_subscription(
    client,
    headers,
    customer: dict,
    cat: dict,
    *,
    start: date | None = None,
    expiry: date | None = None,
    quantity: int = 1,
    terms: str = "net_30",
    activate: bool = True,
) -> dict:
    """Create -> send-quotation -> confirm -> (activate) through the API; returns the subscription JSON."""
    start = start or TODAY
    r = client.post(
        f"{API}/subscriptions",
        headers=headers,
        json={
            "customerId": customer["id"],
            "planId": cat["plan"],
            "startDate": str(start),
            "expiryDate": str(expiry or start + timedelta(days=365)),
            "paymentTerms": terms,
            "lines": [{"productId": cat["product"], "variantId": cat["variant"], "quantity": quantity}],
        },
    )
    assert r.status_code == 201, r.text
    sub = r.json()
    steps = ["send-quotation", "confirm"] + (["activate"] if activate else [])
    for step in steps:
        r = client.post(f"{API}/subscriptions/{sub['id']}/{step}", headers=headers)
        assert r.status_code == 200, f"{step}: {r.text}"
        sub = r.json()
    return sub


def run_billing(client, headers, subscription_ids: list[str], *, as_of: date | None = None, dry_run: bool = False) -> dict:
    """POST /billing/run limited to the given subscriptions (never bill the shared database's other rows)."""
    body: dict = {"subscriptionIds": subscription_ids, "dryRun": dry_run}
    if as_of is not None:
        body["asOf"] = str(as_of)
    r = client.post(f"{API}/billing/run", headers=headers, json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    if not dry_run:
        TRACKED_RUNS.add(result["runId"])
    return result


def set_subscription(subscription_id: str, **columns) -> None:
    """Direct SQL for states the API will not produce (e.g. an expiry in the past)."""
    sets = ", ".join(f"{k} = :{k}" for k in columns)
    with engine.begin() as c:
        c.execute(text(f"update subscriptions set {sets} where id = :id"), {"id": subscription_id, **columns})


def next_billing_date(client, headers, subscription_id: str) -> str | None:
    return client.get(f"{API}/subscriptions/{subscription_id}", headers=headers).json()["nextBillingDate"]


def invoices_of(client, headers, subscription_id: str) -> list[dict]:
    r = client.get(f"{API}/subscriptions/{subscription_id}/invoices?limit=100", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def periods_until(start: date, as_of: date, expiry: date, billing_period: str = "monthly") -> list[date]:
    """Period starts a correct run bills: from `start` while <= as_of and < expiry (exclusive)."""
    out, d = [], start
    while d <= as_of and d < expiry:
        out.append(d)
        d = add_period(d, billing_period)
    return out
