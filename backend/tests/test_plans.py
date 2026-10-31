import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header
from tests.helpers import API, CATALOGUE_PREFIX as TEST_PREFIX, MISSING_ID, admin_headers, make_staff

TODAY = date.today()


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(text("delete from plans where name like :p"), {"p": f"{TEST_PREFIX}%"})


@pytest.fixture(scope="module", autouse=True)
def _clean_plans():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def _plan(client, admin, **overrides):
    body = {
        "name": f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}",
        "price": "99.00",
        "billingPeriod": "monthly",
        "minQuantity": 1,
        "availableFrom": str(TODAY - timedelta(days=1)),
        **overrides,
    }
    r = client.post(f"{API}/plans", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_returns_contract_shape_with_defaults(client, admin):
    p = _plan(client, admin)
    assert set(p) == {
        "id", "name", "price", "billingPeriod", "minQuantity", "availableFrom", "availableTo", "autoClose",
        "allowEarlyClose", "allowPause", "allowRenew", "isActive", "createdAt",
    }  # fmt: skip
    assert p["price"] == "99.00" and p["availableTo"] is None
    assert (p["autoClose"], p["allowEarlyClose"], p["allowPause"], p["allowRenew"], p["isActive"]) == (
        False, False, False, True, True
    )  # fmt: skip
    assert client.get(f"{API}/plans/{p['id']}", headers=admin).json() == p


def test_validation(client, admin):
    base = {"name": f"{TEST_PREFIX}bad", "price": "1.00", "billingPeriod": "monthly", "availableFrom": str(TODAY)}
    for bad in ({"billingPeriod": "hourly"}, {"minQuantity": 0}, {"price": "-1"}, {"name": ""}):
        r = client.post(f"{API}/plans", json={**base, **bad}, headers=admin)
        assert r.status_code == 400, (bad, r.text)
    assert client.post(f"{API}/plans", json={"name": "x"}, headers=admin).status_code == 400


def test_end_date_before_start_is_422(client, admin):
    body = {
        "name": f"{TEST_PREFIX}dates", "price": "1.00", "billingPeriod": "daily",
        "availableFrom": "2026-06-01", "availableTo": "2026-05-31",
    }  # fmt: skip
    r = client.post(f"{API}/plans", json=body, headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    p = _plan(client, admin, availableFrom="2026-06-01")
    r = client.patch(f"{API}/plans/{p['id']}", json={"availableTo": "2026-01-01"}, headers=admin)
    assert r.status_code == 422


def test_roles(client, admin, new_user):
    p = _plan(client, admin)
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    for headers in (staff, auth_header(signed_up["token"])):
        assert client.get(f"{API}/plans", headers=headers).status_code == 200
        assert client.get(f"{API}/plans/{p['id']}", headers=headers).status_code == 200
        assert client.post(f"{API}/plans", json={}, headers=headers).status_code == 403
        assert client.patch(f"{API}/plans/{p['id']}", json={"name": "z"}, headers=headers).status_code == 403
        assert client.delete(f"{API}/plans/{p['id']}", headers=headers).status_code == 403
    assert client.get(f"{API}/plans").status_code == 401


def test_customers_only_see_active_plans_inside_their_dates(client, admin, new_user):
    tag = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"
    open_plan = _plan(client, admin, name=f"{tag}-open")
    future = _plan(client, admin, name=f"{tag}-future", availableFrom=str(TODAY + timedelta(days=5)))
    past = _plan(
        client, admin, name=f"{tag}-past",
        availableFrom=str(TODAY - timedelta(days=9)), availableTo=str(TODAY - timedelta(days=1)),
    )  # fmt: skip
    ends_today = _plan(client, admin, name=f"{tag}-today", availableTo=str(TODAY))
    off = _plan(client, admin, name=f"{tag}-off", isActive=False)

    _, _, signed_up = new_user("shopper")
    customer = auth_header(signed_up["token"])
    seen = client.get(f"{API}/plans", params={"q": tag, "isActive": "false"}, headers=customer).json()["data"]
    assert {p["id"] for p in seen} == {open_plan["id"], ends_today["id"]}
    for hidden in (future, past, off):
        assert client.get(f"{API}/plans/{hidden['id']}", headers=customer).status_code == 404

    everything = client.get(f"{API}/plans", params={"q": tag, "limit": 100}, headers=admin).json()
    assert everything["meta"]["total"] == 5
    only_off = client.get(f"{API}/plans", params={"q": tag, "isActive": "false"}, headers=admin).json()["data"]
    assert [p["id"] for p in only_off] == [off["id"]]


def test_filter_by_billing_period_and_paginate(client, admin):
    tag = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"
    for i, period in enumerate(["daily", "weekly", "weekly"]):
        _plan(client, admin, name=f"{tag}-{i}", billingPeriod=period)
    weekly = client.get(f"{API}/plans", params={"q": tag, "billingPeriod": "weekly", "limit": 1}, headers=admin).json()
    assert weekly["meta"] == {"page": 1, "limit": 1, "total": 2, "totalPages": 2}
    assert client.get(f"{API}/plans", params={"billingPeriod": "hourly"}, headers=admin).status_code == 400


def test_patch_is_partial_and_can_clear_end_date(client, admin):
    p = _plan(client, admin, availableTo=str(TODAY + timedelta(days=30)), allowPause=True)
    r = client.patch(f"{API}/plans/{p['id']}", json={"price": "120.50", "allowRenew": False}, headers=admin)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["price"] == "120.50" and u["allowRenew"] is False
    assert u["allowPause"] is True and u["availableTo"] == p["availableTo"] and u["name"] == p["name"]
    cleared = client.patch(f"{API}/plans/{p['id']}", json={"availableTo": None}, headers=admin).json()
    assert cleared["availableTo"] is None
    assert client.patch(f"{API}/plans/{p['id']}", json={"name": None}, headers=admin).status_code == 400
    assert client.patch(f"{API}/plans/{MISSING_ID}", json={"name": "z"}, headers=admin).status_code == 404


def test_deactivate_is_soft_and_idempotent(client, admin):
    p = _plan(client, admin)
    assert client.delete(f"{API}/plans/{p['id']}", headers=admin).status_code == 204
    assert client.get(f"{API}/plans/{p['id']}", headers=admin).json()["isActive"] is False
    assert client.delete(f"{API}/plans/{p['id']}", headers=admin).status_code == 204
    assert client.delete(f"{API}/plans/{MISSING_ID}", headers=admin).status_code == 404
