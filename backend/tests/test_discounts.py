import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header
from tests.helpers import API, CATALOGUE_PREFIX, MISSING_ID, admin_headers, make_staff

TODAY = date.today()
SEED_PRODUCT = "Brightloop CRM"


def _cleanup() -> None:
    with engine.begin() as conn:  # link rows cascade
        conn.execute(text("delete from discounts where name like :p"), {"p": f"{CATALOGUE_PREFIX}%"})
        conn.execute(text("delete from products where name like :p"), {"p": f"{CATALOGUE_PREFIX}%"})


@pytest.fixture(scope="module", autouse=True)
def _clean_discounts():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


@pytest.fixture(scope="module")
def product_ids(client, admin):
    ids = []
    for i in range(2):
        body = {"name": f"{CATALOGUE_PREFIX}disc-prod-{i}", "type": "software", "salesPrice": "10.00", "costPrice": "5.00"}
        r = client.post(f"{API}/products", json=body, headers=admin)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


@pytest.fixture(scope="module")
def subscription_id():
    with engine.connect() as conn:
        found = conn.execute(text("select id from subscriptions limit 1")).scalar()
    if found is None:
        pytest.skip("the seed has no subscription to link a discount to")
    return str(found)


def _discount(client, admin, expect=201, **overrides):
    body = {
        "name": f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}",
        "type": "percentage",
        "value": 10,
        "scope": "subscriptions",
        "startDate": str(TODAY - timedelta(days=1)),
        **overrides,
    }
    r = client.post(f"{API}/discounts", json=body, headers=admin)
    assert r.status_code == expect, r.text
    return r.json()


def test_create_returns_contract_shape(client, admin, product_ids):
    d = _discount(
        client, admin, scope="products", productIds=product_ids, value=12.5,
        minPurchaseAmount="100.00", minQuantity=3, endDate=str(TODAY + timedelta(days=30)), usageLimit=5,
    )  # fmt: skip
    assert set(d) == {
        "id", "name", "type", "value", "scope", "minPurchaseAmount", "minQuantity", "startDate", "endDate",
        "usageLimit", "usedCount", "status", "productIds", "subscriptionIds", "isActive",
    }  # fmt: skip
    assert d["value"] == 12.5 and d["minPurchaseAmount"] == "100.00" and d["minQuantity"] == 3
    assert d["usedCount"] == 0 and d["status"] == "running" and d["isActive"] is True
    assert d["productIds"] == sorted(product_ids) and d["subscriptionIds"] == []
    assert client.get(f"{API}/discounts/{d['id']}", headers=admin).json() == d


def test_optional_fields_default_to_null(client, admin):
    d = _discount(client, admin)
    assert d["minPurchaseAmount"] is None and d["minQuantity"] is None
    assert d["endDate"] is None and d["usageLimit"] is None
    assert d["productIds"] == [] and d["subscriptionIds"] == []  # no subscriptions listed = all subscriptions


def test_seeded_discount_is_listed(client, admin):
    found = client.get(f"{API}/discounts", params={"limit": 100}, headers=admin).json()["data"]
    seeded = next(d for d in found if d["scope"] == "products" and d["type"] == "percentage" and d["value"] == 10)
    assert seeded["productIds"]


def test_validation(client, admin):
    base = {"name": f"{CATALOGUE_PREFIX}bad", "type": "fixed", "value": 5, "scope": "subscriptions", "startDate": str(TODAY)}
    for bad in (
        {"type": "weird"}, {"scope": "everything"}, {"value": -1}, {"name": ""}, {"name": "   "}, {"minQuantity": 0},
        {"usageLimit": 0}, {"startDate": "not-a-date"}, {"minPurchaseAmount": "-5.00"},
    ):  # fmt: skip
        r = client.post(f"{API}/discounts", json={**base, **bad}, headers=admin)
        assert r.status_code == 400, (bad, r.text)
    assert client.post(f"{API}/discounts", json={"name": "x"}, headers=admin).status_code == 400


def test_business_rules_are_422(client, admin, product_ids):
    _discount(client, admin, expect=422, value=100.5)  # percentage over 100
    fixed = _discount(client, admin, type="fixed", value=500)  # fixed amounts may exceed 100
    assert fixed["value"] == 500
    _discount(client, admin, expect=422, startDate="2026-06-01", endDate="2026-05-31")
    _discount(client, admin, expect=422, scope="products", productIds=[])  # products scope needs products
    _discount(client, admin, expect=422, scope="products", productIds=[MISSING_ID])
    _discount(client, admin, expect=422, subscriptionIds=[MISSING_ID])


def test_scope_keeps_only_matching_links(client, admin, product_ids, subscription_id):
    by_subscription = _discount(client, admin, productIds=product_ids, subscriptionIds=[subscription_id])
    assert by_subscription["productIds"] == [] and by_subscription["subscriptionIds"] == [subscription_id]
    by_product = _discount(client, admin, scope="products", productIds=product_ids, subscriptionIds=[subscription_id])
    assert by_product["subscriptionIds"] == [] and by_product["productIds"] == sorted(product_ids)


def test_roles(client, admin, new_user):
    d = _discount(client, admin)
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    assert client.get(f"{API}/discounts", headers=staff).status_code == 200
    assert client.get(f"{API}/discounts/{d['id']}", headers=staff).status_code == 200
    assert client.post(f"{API}/discounts", json={}, headers=staff).status_code == 403
    assert client.patch(f"{API}/discounts/{d['id']}", json={"name": "z"}, headers=staff).status_code == 403
    assert client.delete(f"{API}/discounts/{d['id']}", headers=staff).status_code == 403
    customer = auth_header(signed_up["token"])
    assert client.get(f"{API}/discounts", headers=customer).status_code == 403
    assert client.get(f"{API}/discounts/{d['id']}", headers=customer).status_code == 403
    assert client.get(f"{API}/discounts").status_code == 401


def test_status_is_derived(client, admin):
    scheduled = _discount(client, admin, startDate=str(TODAY + timedelta(days=3)))
    expired = _discount(client, admin, startDate=str(TODAY - timedelta(days=9)), endDate=str(TODAY - timedelta(days=1)))
    ends_today = _discount(client, admin, endDate=str(TODAY))
    off = _discount(client, admin, isActive=False)
    assert [x["status"] for x in (scheduled, expired, ends_today, off)] == ["scheduled", "expired", "running", "inactive"]

    exhausted = _discount(client, admin, usageLimit=2)
    with engine.begin() as conn:  # used_count is trigger-owned in the app; tests set it directly to reach 'exhausted'
        conn.execute(text("update discounts set used_count = 2 where id = :i"), {"i": exhausted["id"]})
    again = client.get(f"{API}/discounts/{exhausted['id']}", headers=admin).json()
    assert again["status"] == "exhausted" and again["usedCount"] == 2


def test_list_filters_and_pagination(client, admin):
    tag = f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}"
    running = _discount(client, admin, name=f"{tag}-run")
    future = _discount(client, admin, name=f"{tag}-future", startDate=str(TODAY + timedelta(days=3)))
    past = _discount(client, admin, name=f"{tag}-past", startDate="2020-01-01", endDate="2020-12-31")
    off = _discount(client, admin, name=f"{tag}-off", isActive=False)
    full = _discount(client, admin, name=f"{tag}-full", usageLimit=1)
    with engine.begin() as conn:
        conn.execute(text("update discounts set used_count = 1 where id = :i"), {"i": full["id"]})

    def ids(**params):
        r = client.get(f"{API}/discounts", params={"q": tag, "limit": 100, **params}, headers=admin)
        assert r.status_code == 200, r.text
        return {d["id"] for d in r.json()["data"]}

    assert ids() == {running["id"], future["id"], past["id"], off["id"], full["id"]}
    assert ids(isActive="false") == {off["id"]}
    assert ids(validOn=str(TODAY)) == {running["id"]}  # inside dates, active, not used up
    assert ids(validOn=str(TODAY + timedelta(days=3))) == {running["id"], future["id"]}
    assert ids(validOn="2020-06-01") == {past["id"]}  # the others start later
    page = client.get(f"{API}/discounts", params={"q": tag, "limit": 2}, headers=admin).json()
    assert page["meta"] == {"page": 1, "limit": 2, "total": 5, "totalPages": 3} and len(page["data"]) == 2
    assert client.get(f"{API}/discounts", params={"validOn": "tomorrow"}, headers=admin).status_code == 400


def test_patch_is_partial_and_clears_nullable_fields(client, admin):
    d = _discount(client, admin, minQuantity=4, endDate=str(TODAY + timedelta(days=10)), usageLimit=7)
    r = client.patch(f"{API}/discounts/{d['id']}", json={"value": 15, "usageLimit": None, "endDate": None}, headers=admin)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["value"] == 15 and u["usageLimit"] is None and u["endDate"] is None
    assert u["minQuantity"] == 4 and u["name"] == d["name"] and u["scope"] == "subscriptions"
    assert client.patch(f"{API}/discounts/{d['id']}", json={"name": None}, headers=admin).status_code == 400
    assert client.patch(f"{API}/discounts/{MISSING_ID}", json={"name": "z"}, headers=admin).status_code == 404


def test_patch_cannot_edit_used_count_or_break_rules(client, admin):
    d = _discount(client, admin, usageLimit=5)
    assert client.patch(f"{API}/discounts/{d['id']}", json={"usedCount": 3}, headers=admin).json()["usedCount"] == 0
    with engine.begin() as conn:
        conn.execute(text("update discounts set used_count = 3 where id = :i"), {"i": d["id"]})
    low = client.patch(f"{API}/discounts/{d['id']}", json={"usageLimit": 2}, headers=admin)
    assert low.status_code == 422 and low.json()["error"]["code"] == "BUSINESS_RULE"
    assert client.patch(f"{API}/discounts/{d['id']}", json={"usageLimit": 3}, headers=admin).status_code == 200
    # switching an existing percentage rule to a bigger value, or crossing the dates, is rejected on the merged state
    assert client.patch(f"{API}/discounts/{d['id']}", json={"value": 101}, headers=admin).status_code == 422
    assert client.patch(f"{API}/discounts/{d['id']}", json={"endDate": "2000-01-01"}, headers=admin).status_code == 422


def test_patch_links_and_scope_switch(client, admin, product_ids, subscription_id):
    d = _discount(client, admin, scope="products", productIds=product_ids)
    one = client.patch(f"{API}/discounts/{d['id']}", json={"productIds": product_ids[:1]}, headers=admin).json()
    assert one["productIds"] == product_ids[:1]
    kept = client.patch(f"{API}/discounts/{d['id']}", json={"name": f"{d['name']}-b"}, headers=admin).json()
    assert kept["productIds"] == product_ids[:1]  # untouched when not sent
    assert client.patch(f"{API}/discounts/{d['id']}", json={"productIds": []}, headers=admin).status_code == 422

    switched = client.patch(
        f"{API}/discounts/{d['id']}", json={"scope": "subscriptions", "subscriptionIds": [subscription_id]}, headers=admin
    ).json()
    assert switched["scope"] == "subscriptions"
    assert switched["productIds"] == [] and switched["subscriptionIds"] == [subscription_id]
    all_subs = client.patch(f"{API}/discounts/{d['id']}", json={"subscriptionIds": []}, headers=admin).json()
    assert all_subs["subscriptionIds"] == []
    back = client.patch(f"{API}/discounts/{d['id']}", json={"scope": "products"}, headers=admin)
    assert back.status_code == 422  # a products scope with no products


def test_deactivate_is_soft_and_idempotent(client, admin):
    d = _discount(client, admin)
    assert client.delete(f"{API}/discounts/{d['id']}", headers=admin).status_code == 204
    gone = client.get(f"{API}/discounts/{d['id']}", headers=admin).json()
    assert gone["isActive"] is False and gone["status"] == "inactive"
    assert client.delete(f"{API}/discounts/{d['id']}", headers=admin).status_code == 204
    assert client.delete(f"{API}/discounts/{MISSING_ID}", headers=admin).status_code == 404
