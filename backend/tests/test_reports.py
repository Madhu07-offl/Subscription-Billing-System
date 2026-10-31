"""Reports are read-only views over invoices and payments, which other modules own. These tests seed their own
rows with SQL in 2020 (far from real data) and narrow every call with customerId, so other rows never interfere.
The customer email deliberately does NOT start with 'pytest-': conftest wipes those customers at session start,
which would fail on the foreign keys if a crashed run had left invoices behind."""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header
from tests.helpers import API, CATALOGUE_PREFIX, admin_headers, make_staff

EMAIL = f"reports-{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}@example.com"
SEED_PRODUCT = "00000000-0000-4000-8000-000000000201"
YEAR = {"from": "2020-01-01", "to": "2020-12-31"}


def _cleanup() -> None:
    with engine.begin() as conn:
        like = {"e": "reports-" + CATALOGUE_PREFIX + "%", "p": CATALOGUE_PREFIX + "%"}
        conn.execute(
            text("delete from payments where invoice_id in (select i.id from invoices i "
                 "join customers c on c.id = i.customer_id where c.email like :e)"), like)  # fmt: skip
        conn.execute(text("delete from invoices where customer_id in (select id from customers where email like :e)"), like)
        conn.execute(text("delete from subscriptions where customer_id in (select id from customers where email like :e)"), like)
        conn.execute(text("delete from customers where email like :e"), like)
        conn.execute(text("delete from plans where name like :p"), like)


@pytest.fixture(scope="module", autouse=True)
def data():
    """customer; plan A (monthly, 200/month) and plan B (yearly, 1200/year); invoices and payments in 2020."""
    _cleanup()
    ids = {}
    with engine.begin() as conn:

        def one(sql, **params):
            return str(conn.execute(text(sql), params).scalar_one())

        ids["customer"] = one("insert into customers (name, email) values ('Reports Co', :e) returning id", e=EMAIL)
        for key, period, unit_price in (("a", "monthly", 100), ("b", "yearly", 600)):
            plan = one(
                "insert into plans (name, price, billing_period, available_from) values (:n, 1, :b, '2020-01-01') returning id",
                n=f"{CATALOGUE_PREFIX}rep-{key}", b=period,
            )  # fmt: skip
            sub = one(
                "insert into subscriptions (customer_id, plan_id, status, start_date, expiry_date, next_billing_date) "
                "values (:c, :p, 'active', '2020-01-01', '2099-01-01', '2099-01-01') returning id",
                c=ids["customer"], p=plan,
            )  # fmt: skip
            conn.execute(
                text(
                    "insert into subscription_lines (subscription_id, product_id, product_name, quantity, unit_price) "
                    "values (:s, :pr, 'Brightloop CRM', 2, cast(:u as numeric))"
                ),
                {"s": sub, "pr": SEED_PRODUCT, "u": unit_price},
            )
            ids[f"plan_{key}"], ids[f"sub_{key}"] = plan, sub

        def invoice(sub, start, status, issue, due, subtotal, tax=0):
            return one(
                "insert into invoices (subscription_id, customer_id, period_start, period_end, status, issue_date, "
                "due_date, subtotal, tax_total, total) "
                "values (:s, :c, :ps, :ps, :st, :i, :d, cast(:sub as numeric), cast(:tax as numeric), cast(:sub as numeric) + cast(:tax as numeric)) returning id",
                s=sub, c=ids["customer"], ps=start, st=status, i=issue, d=due, sub=subtotal, tax=tax,
            )  # fmt: skip

        def pay(inv, method, amount, day):
            return one(
                "insert into payments (invoice_id, method, amount, payment_date) values (:i, :m, cast(:a as numeric), :d) returning id",
                i=inv, m=method, a=amount, d=day,
            )  # fmt: skip

        i1 = invoice(ids["sub_a"], "2020-01-01", "confirmed", "2020-01-10", "2020-02-09", 100, 18)  # total 118, overdue
        pay(i1, "cash", 50, "2020-01-20")
        voided = pay(i1, "bank_transfer", 30, "2020-01-25")
        conn.execute(text("update payments set voided_at = now() where id = :i"), {"i": voided})
        i2 = invoice(ids["sub_a"], "2020-02-01", "confirmed", "2020-02-05", "2020-02-05", 200)
        pay(i2, "card", 200, "2020-02-06")  # trigger flips it to paid
        invoice(ids["sub_a"], "2020-03-01", "draft", None, None, 999)  # never counted as revenue
        i4 = invoice(ids["sub_a"], "2020-04-01", "confirmed", "2020-04-01", "2020-04-01", 777)
        conn.execute(text("update invoices set status = 'cancelled' where id = :i"), {"i": i4})
        invoice(ids["sub_b"], "2020-01-01", "confirmed", "2020-01-15", "2099-01-01", 1000)  # open, not overdue
    yield ids
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def _summary(client, admin, **params):
    r = client.get(f"{API}/reports/summary", params=params, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_shape_without_filters(client, admin):
    s = _summary(client, admin)
    assert set(s) == {
        "period", "subscriptions", "mrr", "revenueInvoiced", "revenueCollected", "outstanding", "overdue",
        "invoicesByStatus", "paymentsByMethod",
    }  # fmt: skip
    today = date.today()
    assert s["period"] == {"from": str(today.replace(day=1)), "to": str(today)}
    assert set(s["subscriptions"]["byStatus"]) >= {"draft", "quotation", "confirmed", "active", "closed"}
    assert s["subscriptions"]["active"] == s["subscriptions"]["byStatus"]["active"]
    for key in ("mrr", "revenueInvoiced", "revenueCollected", "outstanding"):
        assert isinstance(s[key], str) and s[key].count(".") == 1 and len(s[key].split(".")[1]) == 2
    assert set(s["overdue"]) == {"count", "amount"}


def test_summary_for_one_customer_over_a_year(client, admin, data):
    s = _summary(client, admin, customerId=data["customer"], **YEAR)
    assert s["period"] == {"from": "2020-01-01", "to": "2020-12-31"}
    assert s["subscriptions"] == {"active": 2, "byStatus": {"draft": 0, "quotation": 0, "confirmed": 0, "active": 2, "closed": 0}}
    assert s["mrr"] == "300.00"  # 200 monthly + 1200 yearly / 12
    assert s["revenueInvoiced"] == "1318.00"  # 118 + 200 + 1000; draft and cancelled excluded
    assert s["revenueCollected"] == "250.00"  # 50 + 200; the voided 30 is excluded
    assert s["outstanding"] == "1068.00"  # 68 left on invoice 1 + 1000 open; the paid invoice owes nothing
    assert s["overdue"] == {"count": 1, "amount": "68.00"}
    assert s["invoicesByStatus"] == {"draft": 1, "confirmed": 2, "paid": 1, "cancelled": 1}
    assert s["paymentsByMethod"] == [
        {"method": "card", "count": 1, "amount": "200.00"},
        {"method": "cash", "count": 1, "amount": "50.00"},
    ]


def test_period_only_narrows_revenue_figures(client, admin, data):
    s = _summary(client, admin, customerId=data["customer"], **{"from": "2020-02-01", "to": "2020-02-29"})
    assert s["revenueInvoiced"] == "200.00" and s["revenueCollected"] == "200.00"
    assert s["paymentsByMethod"] == [{"method": "card", "count": 1, "amount": "200.00"}]
    assert s["outstanding"] == "1068.00" and s["mrr"] == "300.00"  # as of today, not the period
    empty = _summary(client, admin, customerId=data["customer"], **{"from": "2019-01-01", "to": "2019-12-31"})
    assert empty["revenueInvoiced"] == "0.00" and empty["revenueCollected"] == "0.00" and empty["paymentsByMethod"] == []


def test_plan_filter(client, admin, data):
    a = _summary(client, admin, customerId=data["customer"], planId=data["plan_a"], **YEAR)
    assert (a["mrr"], a["revenueInvoiced"], a["revenueCollected"], a["outstanding"]) == ("200.00", "318.00", "250.00", "68.00")
    assert a["overdue"]["count"] == 1 and a["subscriptions"]["active"] == 1
    b = _summary(client, admin, customerId=data["customer"], planId=data["plan_b"], **YEAR)
    assert (b["mrr"], b["revenueInvoiced"], b["revenueCollected"], b["outstanding"]) == ("100.00", "1000.00", "0.00", "1000.00")
    assert b["overdue"] == {"count": 0, "amount": "0.00"} and b["paymentsByMethod"] == []
    nothing = _summary(client, admin, customerId=str(uuid.uuid4()))
    assert nothing["mrr"] == "0.00" and nothing["subscriptions"]["active"] == 0


def test_revenue_monthly_fills_gaps(client, admin, data):
    params = {"customerId": data["customer"], "from": "2020-01-01", "to": "2020-04-30"}
    r = client.get(f"{API}/reports/revenue", params=params, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "data": [
            {"period": "2020-01-01", "invoiced": "1118.00", "collected": "50.00"},
            {"period": "2020-02-01", "invoiced": "200.00", "collected": "200.00"},
            {"period": "2020-03-01", "invoiced": "0.00", "collected": "0.00"},
            {"period": "2020-04-01", "invoiced": "0.00", "collected": "0.00"},  # cancelled invoice is not revenue
        ]
    }
    only_b = client.get(f"{API}/reports/revenue", params={**params, "planId": data["plan_b"]}, headers=admin).json()
    assert only_b["data"][0] == {"period": "2020-01-01", "invoiced": "1000.00", "collected": "0.00"}


def test_revenue_by_week_and_day(client, admin, data):
    base = {"customerId": data["customer"], "from": "2020-01-08", "to": "2020-01-19"}
    weeks = client.get(f"{API}/reports/revenue", params={**base, "groupBy": "week"}, headers=admin).json()["data"]
    assert weeks == [  # weeks start on Monday
        {"period": "2020-01-06", "invoiced": "118.00", "collected": "0.00"},
        {"period": "2020-01-13", "invoiced": "1000.00", "collected": "0.00"},
    ]
    days = client.get(
        f"{API}/reports/revenue",
        params={"customerId": data["customer"], "from": "2020-01-09", "to": "2020-01-11", "groupBy": "day"},
        headers=admin,
    ).json()["data"]
    assert [d["period"] for d in days] == ["2020-01-09", "2020-01-10", "2020-01-11"]
    assert [d["invoiced"] for d in days] == ["0.00", "118.00", "0.00"]


def test_revenue_default_period_and_validation(client, admin):
    today = date.today()
    r = client.get(f"{API}/reports/revenue", headers=admin).json()["data"]
    assert [p["period"] for p in r] == [str(today.replace(day=1))]  # this month, grouped by month
    bad_range = client.get(f"{API}/reports/revenue", params={"from": "2020-02-01", "to": "2020-01-01"}, headers=admin)
    assert bad_range.status_code == 400 and bad_range.json()["error"]["details"][0]["field"] == "from"
    assert client.get(f"{API}/reports/summary", params={"from": "2020-02-01", "to": "2020-01-01"}, headers=admin).status_code == 400
    assert client.get(f"{API}/reports/revenue", params={"groupBy": "year"}, headers=admin).status_code == 400
    assert client.get(f"{API}/reports/revenue", params={"planId": "nope"}, headers=admin).status_code == 400
    too_wide = {"from": "2000-01-01", "to": "2026-01-01", "groupBy": "day"}
    assert client.get(f"{API}/reports/revenue", params=too_wide, headers=admin).status_code == 400


def test_roles(client, admin, new_user):
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    for path in ("summary", "revenue"):
        assert client.get(f"{API}/reports/{path}", headers=staff).status_code == 200
        assert client.get(f"{API}/reports/{path}", headers=auth_header(signed_up["token"])).status_code == 403
        assert client.get(f"{API}/reports/{path}").status_code == 401


def test_summary_is_fast(client, admin):
    import time

    started = time.perf_counter()
    assert client.get(f"{API}/reports/summary", headers=admin).status_code == 200
    assert client.get(f"{API}/reports/revenue", params={"from": "2020-01-01", "to": "2026-12-31"}, headers=admin).status_code == 200
    assert time.perf_counter() - started < 2
