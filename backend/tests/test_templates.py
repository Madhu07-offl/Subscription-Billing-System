import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header
from tests.helpers import API, CATALOGUE_PREFIX, MISSING_ID, admin_headers, make_staff


def _cleanup() -> None:
    with engine.begin() as conn:
        pattern = {"p": f"{CATALOGUE_PREFIX}%"}
        conn.execute(text("delete from quotation_templates where name like :p"), pattern)  # lines cascade
        conn.execute(text("delete from products where name like :p"), pattern)
        conn.execute(text("delete from plans where name like :p"), pattern)


@pytest.fixture(scope="module", autouse=True)
def _clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


@pytest.fixture(scope="module")
def plan(client, admin):
    body = {"name": f"{CATALOGUE_PREFIX}tpl-plan", "price": "10.00", "billingPeriod": "monthly", "availableFrom": str(date.today())}
    r = client.post(f"{API}/plans", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="module")
def product(client, admin):
    body = {
        "name": f"{CATALOGUE_PREFIX}tpl-prod", "type": "software", "salesPrice": "100.00", "costPrice": "40.00",
        "variants": [{"attribute": "Brand", "value": "Odoo", "extraPrice": "560.00"}],
    }  # fmt: skip
    r = client.post(f"{API}/products", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _template(client, admin, plan, product, expect=201, **overrides):
    body = {
        "name": f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}",
        "planId": plan["id"],
        "validityDays": 30,
        "lines": [{"productId": product["id"], "quantity": 2}],
        **overrides,
    }
    r = client.post(f"{API}/quotation-templates", json=body, headers=admin)
    assert r.status_code == expect, r.text
    return r.json()


def test_create_returns_contract_shape(client, admin, plan, product):
    variant_id = product["variants"][0]["id"]
    lines = [{"productId": product["id"], "variantId": variant_id, "quantity": 1}, {"productId": product["id"], "quantity": 5}]
    t = _template(client, admin, plan, product, lines=lines, notes="n")
    assert set(t) == {"id", "name", "planId", "planName", "validityDays", "lines", "notes", "createdAt"}
    assert t["planName"] == plan["name"] and t["validityDays"] == 30 and t["notes"] == "n"
    assert t["lines"] == [lines[0], {**lines[1], "variantId": None}]  # order preserved; variantId null when not chosen
    assert client.get(f"{API}/quotation-templates/{t['id']}", headers=admin).json() == t


def test_validation(client, admin, plan, product):
    base = {"name": f"{CATALOGUE_PREFIX}bad", "planId": plan["id"], "validityDays": 30, "lines": []}
    line = {"productId": product["id"], "quantity": 1}
    for bad in (
        {"name": ""}, {"name": "   "}, {"validityDays": 0}, {"planId": "nope"}, {"lines": [{**line, "quantity": 0}]},
        {"lines": [{"quantity": 1}]},
    ):  # fmt: skip
        r = client.post(f"{API}/quotation-templates", json={**base, **bad}, headers=admin)
        assert r.status_code == 400, (bad, r.text)
    assert client.post(f"{API}/quotation-templates", json={"name": "x"}, headers=admin).status_code == 400


def test_reference_rules_are_422(client, admin, plan, product):
    line = {"productId": product["id"], "quantity": 1}
    _template(client, admin, plan, product, expect=422, planId=MISSING_ID)
    _template(client, admin, plan, product, expect=422, lines=[{"productId": MISSING_ID, "quantity": 1}])
    _template(client, admin, plan, product, expect=422, lines=[{**line, "variantId": MISSING_ID}])

    other = client.post(
        f"{API}/products",
        json={"name": f"{CATALOGUE_PREFIX}other", "type": "goods", "salesPrice": "1.00", "costPrice": "1.00"},
        headers=admin,
    ).json()
    foreign_variant = product["variants"][0]["id"]
    _template(client, admin, plan, other, expect=422, lines=[{"productId": other["id"], "variantId": foreign_variant, "quantity": 1}])

    client.delete(f"{API}/products/{other['id']}", headers=admin)  # archived products cannot be added
    _template(client, admin, plan, other, expect=422)


def test_archived_variant_is_rejected(client, admin, plan):
    p = client.post(
        f"{API}/products",
        json={"name": f"{CATALOGUE_PREFIX}arch", "type": "addon", "salesPrice": "1.00", "costPrice": "1.00",
              "variants": [{"attribute": "A", "value": "B", "extraPrice": "0"}]},
        headers=admin,
    ).json()  # fmt: skip
    variant_id = p["variants"][0]["id"]
    _template(client, admin, plan, p, lines=[{"productId": p["id"], "variantId": variant_id, "quantity": 1}])
    client.delete(f"{API}/products/{p['id']}/variants/{variant_id}", headers=admin)  # used -> archived
    again = {"productId": p["id"], "variantId": variant_id, "quantity": 1}
    _template(client, admin, plan, p, expect=422, lines=[again])


def test_roles(client, admin, plan, product, new_user):
    t = _template(client, admin, plan, product)
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    assert client.get(f"{API}/quotation-templates", headers=staff).status_code == 200
    assert client.get(f"{API}/quotation-templates/{t['id']}", headers=staff).status_code == 200
    assert client.post(f"{API}/quotation-templates", json={}, headers=staff).status_code == 403
    assert client.patch(f"{API}/quotation-templates/{t['id']}", json={"name": "z"}, headers=staff).status_code == 403
    assert client.delete(f"{API}/quotation-templates/{t['id']}", headers=staff).status_code == 403
    customer = auth_header(signed_up["token"])
    assert client.get(f"{API}/quotation-templates", headers=customer).status_code == 403
    assert client.get(f"{API}/quotation-templates/{t['id']}", headers=customer).status_code == 403
    assert client.get(f"{API}/quotation-templates").status_code == 401


def test_list_search_and_pagination(client, admin, plan, product):
    tag = f"{CATALOGUE_PREFIX}{uuid.uuid4().hex[:8]}"
    for i in range(3):
        _template(client, admin, plan, product, name=f"{tag}-{i}")
    page = client.get(f"{API}/quotation-templates", params={"q": tag, "limit": 2}, headers=admin).json()
    assert page["meta"] == {"page": 1, "limit": 2, "total": 3, "totalPages": 2} and len(page["data"]) == 2
    assert all(len(t["lines"]) == 1 and t["planName"] == plan["name"] for t in page["data"])


def test_patch_is_partial_and_replaces_lines(client, admin, plan, product):
    t = _template(client, admin, plan, product, notes="keep")
    r = client.patch(f"{API}/quotation-templates/{t['id']}", json={"validityDays": 45}, headers=admin)
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["validityDays"] == 45 and u["notes"] == "keep" and u["name"] == t["name"] and u["lines"] == t["lines"]

    new_lines = [{"productId": product["id"], "quantity": 9}, {"productId": product["id"], "quantity": 1}]
    replaced = client.patch(f"{API}/quotation-templates/{t['id']}", json={"lines": new_lines}, headers=admin).json()
    assert [(ln["quantity"]) for ln in replaced["lines"]] == [9, 1]
    emptied = client.patch(f"{API}/quotation-templates/{t['id']}", json={"lines": []}, headers=admin).json()
    assert emptied["lines"] == []
    assert client.patch(f"{API}/quotation-templates/{t['id']}", json={"notes": None}, headers=admin).json()["notes"] is None


def test_patch_rejections(client, admin, plan, product):
    t = _template(client, admin, plan, product)
    url = f"{API}/quotation-templates/{t['id']}"
    assert client.patch(url, json={"name": None}, headers=admin).status_code == 400
    assert client.patch(url, json={"lines": None}, headers=admin).status_code == 400
    assert client.patch(url, json={"planId": MISSING_ID}, headers=admin).status_code == 422
    bad = {"lines": [{"productId": MISSING_ID, "quantity": 1}]}
    assert client.patch(url, json=bad, headers=admin).status_code == 422
    assert client.get(url, headers=admin).json()["lines"] == t["lines"]  # a rejected patch changes nothing
    assert client.patch(f"{API}/quotation-templates/{MISSING_ID}", json={"name": "z"}, headers=admin).status_code == 404


def test_delete_removes_template_and_lines(client, admin, plan, product):
    t = _template(client, admin, plan, product)
    url = f"{API}/quotation-templates/{t['id']}"
    assert client.delete(url, headers=admin).status_code == 204
    assert client.get(url, headers=admin).status_code == 404
    assert client.delete(url, headers=admin).status_code == 404
    with engine.connect() as conn:
        left = conn.execute(text("select count(*) from quotation_template_lines where template_id = :i"), {"i": t["id"]})
        assert left.scalar() == 0
