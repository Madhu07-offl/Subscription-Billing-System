import uuid

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header
from tests.helpers import API, CATALOGUE_PREFIX, MISSING_ID, admin_headers, make_staff


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(text("delete from taxes where name like :p"), {"p": f"{CATALOGUE_PREFIX}%"})  # types cascade


@pytest.fixture(scope="module", autouse=True)
def _clean_taxes():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def _tax(client, admin, **overrides):
    body = {
        "name": f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}",
        "computation": "percentage",
        "value": 18,
        **overrides,
    }
    r = client.post(f"{API}/taxes", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_returns_contract_shape(client, admin):
    t = _tax(client, admin, value=12.5, appliesToProductTypes=["software", "addon"])
    assert set(t) == {"id", "name", "computation", "value", "appliesToProductTypes", "isActive"}
    assert t["value"] == 12.5 and isinstance(t["value"], float)  # a JSON number, not a string
    assert t["appliesToProductTypes"] == ["addon", "software"] and t["isActive"] is True
    assert client.get(f"{API}/taxes/{t['id']}", headers=admin).json() == t


def test_empty_types_means_every_type_and_duplicates_collapse(client, admin):
    assert _tax(client, admin)["appliesToProductTypes"] == []
    t = _tax(client, admin, appliesToProductTypes=["goods", "goods"])
    assert t["appliesToProductTypes"] == ["goods"]


def test_seeded_gst_is_listed(client, admin):
    taxes = client.get(f"{API}/taxes", params={"limit": 100}, headers=admin).json()["data"]
    gst = next(t for t in taxes if t["name"].startswith("GST"))
    assert gst["computation"] == "percentage" and gst["value"] == 18


def test_validation(client, admin):
    base = {"name": f"{CATALOGUE_PREFIX}bad", "computation": "percentage", "value": 5}
    for bad in ({"computation": "weird"}, {"value": -1}, {"name": ""}, {"name": "   "}, {"appliesToProductTypes": ["gadget"]}):
        r = client.post(f"{API}/taxes", json={**base, **bad}, headers=admin)
        assert r.status_code == 400, (bad, r.text)
    assert client.post(f"{API}/taxes", json={"name": "x"}, headers=admin).status_code == 400


def test_percentage_over_100_is_422_but_fixed_may_exceed(client, admin):
    r = client.post(
        f"{API}/taxes", json={"name": f"{CATALOGUE_PREFIX}big", "computation": "percentage", "value": 101}, headers=admin
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert _tax(client, admin, computation="fixed", value=250)["value"] == 250
    # switching a fixed 250 to percentage without lowering the value must fail too
    fixed = _tax(client, admin, computation="fixed", value=250)
    r = client.patch(f"{API}/taxes/{fixed['id']}", json={"computation": "percentage"}, headers=admin)
    assert r.status_code == 422


def test_roles(client, admin, new_user):
    t = _tax(client, admin)
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    assert client.get(f"{API}/taxes", headers=staff).status_code == 200
    assert client.get(f"{API}/taxes/{t['id']}", headers=staff).status_code == 200
    assert client.post(f"{API}/taxes", json={}, headers=staff).status_code == 403
    assert client.patch(f"{API}/taxes/{t['id']}", json={"name": "z"}, headers=staff).status_code == 403
    assert client.delete(f"{API}/taxes/{t['id']}", headers=staff).status_code == 403
    customer = auth_header(signed_up["token"])
    assert client.get(f"{API}/taxes", headers=customer).status_code == 403
    assert client.get(f"{API}/taxes/{t['id']}", headers=customer).status_code == 403
    assert client.get(f"{API}/taxes").status_code == 401


def test_list_filter_and_pagination(client, admin):
    tag = f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}"
    ids = [_tax(client, admin, name=f"{tag}-{i}")["id"] for i in range(3)]
    client.delete(f"{API}/taxes/{ids[0]}", headers=admin)
    inactive = client.get(f"{API}/taxes", params={"isActive": "false", "limit": 100}, headers=admin).json()["data"]
    assert ids[0] in {t["id"] for t in inactive} and ids[1] not in {t["id"] for t in inactive}
    page = client.get(f"{API}/taxes", params={"isActive": "true", "limit": 2}, headers=admin).json()
    assert page["meta"]["limit"] == 2 and len(page["data"]) == 2
    assert page["meta"]["totalPages"] == -(-page["meta"]["total"] // 2)


def test_patch_is_partial_and_replaces_types(client, admin):
    t = _tax(client, admin, appliesToProductTypes=["software", "goods"])
    r = client.patch(f"{API}/taxes/{t['id']}", json={"value": 5, "appliesToProductTypes": ["goods", "service"]}, headers=admin)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["value"] == 5 and u["appliesToProductTypes"] == ["goods", "service"]
    assert u["name"] == t["name"] and u["computation"] == "percentage"
    untouched = client.patch(f"{API}/taxes/{t['id']}", json={"name": f"{t['name']}-b"}, headers=admin).json()
    assert untouched["appliesToProductTypes"] == ["goods", "service"]
    cleared = client.patch(f"{API}/taxes/{t['id']}", json={"appliesToProductTypes": []}, headers=admin).json()
    assert cleared["appliesToProductTypes"] == []
    assert client.patch(f"{API}/taxes/{t['id']}", json={"name": None}, headers=admin).status_code == 400
    assert client.patch(f"{API}/taxes/{MISSING_ID}", json={"name": "z"}, headers=admin).status_code == 404


def test_deactivate_is_soft_and_idempotent(client, admin):
    t = _tax(client, admin)
    assert client.delete(f"{API}/taxes/{t['id']}", headers=admin).status_code == 204
    assert client.get(f"{API}/taxes/{t['id']}", headers=admin).json()["isActive"] is False
    assert client.delete(f"{API}/taxes/{t['id']}", headers=admin).status_code == 204
    assert client.delete(f"{API}/taxes/{MISSING_ID}", headers=admin).status_code == 404
