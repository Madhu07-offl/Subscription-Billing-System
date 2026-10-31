import uuid

import pytest
from sqlalchemy import text

from app.db import engine
from tests.conftest import TEST_PREFIX, auth_header
from tests.helpers import API, MISSING_ID, admin_headers, make_staff


def _cleanup() -> None:
    with engine.begin() as conn:
        pattern = {"p": f"{TEST_PREFIX}%"}
        conn.execute(text("delete from quotation_templates where name like :p"), pattern)  # lines cascade
        conn.execute(text("delete from products where name like :p"), pattern)  # variants cascade


@pytest.fixture(scope="module", autouse=True)
def _clean_products():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def _product(client, admin, **overrides):
    body = {
        "name": f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}",
        "type": "software",
        "salesPrice": "1000.00",
        "costPrice": "400.00",
        **overrides,
    }
    r = client.post(f"{API}/products", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_with_inline_variants_returns_contract_shape(client, admin):
    p = _product(client, admin, notes="n", variants=[{"attribute": "Brand", "value": "Odoo", "extraPrice": "560.00"}])
    assert set(p) == {"id", "name", "type", "salesPrice", "costPrice", "notes", "isActive", "variants", "createdAt"}
    assert p["salesPrice"] == "1000.00" and p["costPrice"] == "400.00" and p["isActive"] is True
    [v] = p["variants"]
    assert set(v) == {"id", "productId", "attribute", "value", "extraPrice", "isArchived"}
    assert v["productId"] == p["id"] and v["extraPrice"] == "560.00" and v["isArchived"] is False
    assert client.get(f"{API}/products/{p['id']}", headers=admin).json() == p


def test_money_is_two_decimal_string_and_validated(client, admin):
    p = _product(client, admin, salesPrice=12.5)  # a JSON number is accepted but always echoed as "12.50"
    assert p["salesPrice"] == "12.50"
    base = {"name": f"{TEST_PREFIX}bad", "type": "goods", "salesPrice": "1.00", "costPrice": "1.00"}
    for bad in ({"salesPrice": "-1.00"}, {"costPrice": "1.005"}, {"type": "gadget"}, {"name": ""}):
        r = client.post(f"{API}/products", json={**base, **bad}, headers=admin)
        assert r.status_code == 400, (bad, r.text)
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_inline_variants_are_409(client, admin):
    v = {"attribute": "Brand", "value": "Odoo", "extraPrice": "1.00"}
    body = {"name": f"{TEST_PREFIX}dup", "type": "addon", "salesPrice": "1.00", "costPrice": "1.00", "variants": [v, v]}
    assert client.post(f"{API}/products", json=body, headers=admin).status_code == 409


def test_roles(client, admin, new_user):
    p = _product(client, admin)
    _, staff = make_staff(client, admin)
    _, _, signed_up = new_user("shopper")
    customer = auth_header(signed_up["token"])
    body = {"name": f"{TEST_PREFIX}x", "type": "goods", "salesPrice": "1.00", "costPrice": "1.00"}
    for headers in (staff, customer):
        assert client.get(f"{API}/products", headers=headers).status_code == 200
        assert client.get(f"{API}/products/{p['id']}", headers=headers).status_code == 200
        assert client.post(f"{API}/products", json=body, headers=headers).status_code == 403
        assert client.patch(f"{API}/products/{p['id']}", json={"name": "z"}, headers=headers).status_code == 403
        assert client.delete(f"{API}/products/{p['id']}", headers=headers).status_code == 403
        variant = {"attribute": "A", "value": "B", "extraPrice": "0.00"}
        assert client.post(f"{API}/products/{p['id']}/variants", json=variant, headers=headers).status_code == 403
    assert client.get(f"{API}/products").status_code == 401


def test_customers_only_see_active_products(client, admin, new_user):
    p = _product(client, admin)
    _, _, signed_up = new_user("shopper")
    customer = auth_header(signed_up["token"])
    params = {"q": p["name"]}
    assert client.get(f"{API}/products", params=params, headers=customer).json()["meta"]["total"] == 1

    assert client.delete(f"{API}/products/{p['id']}", headers=admin).status_code == 204
    hidden = client.get(f"{API}/products", params={**params, "isActive": "false"}, headers=customer).json()
    assert hidden["data"] == []  # a customer cannot opt in to archived products
    assert client.get(f"{API}/products/{p['id']}", headers=customer).status_code == 404

    seen_by_admin = client.get(f"{API}/products", params={**params, "isActive": "false"}, headers=admin).json()
    assert [x["id"] for x in seen_by_admin["data"]] == [p["id"]]
    assert client.get(f"{API}/products", params={**params, "isActive": "true"}, headers=admin).json()["data"] == []


def test_list_filters_and_pagination(client, admin):
    tag = f"{TEST_PREFIX}{uuid.uuid4().hex[:8]}"
    for i, kind in enumerate(["software", "software", "service"]):
        _product(client, admin, name=f"{tag}-{i}", type=kind)
    body = client.get(f"{API}/products", params={"q": tag, "limit": 2}, headers=admin).json()
    assert body["meta"] == {"page": 1, "limit": 2, "total": 3, "totalPages": 2} and len(body["data"]) == 2
    only_service = client.get(f"{API}/products", params={"q": tag, "type": "service"}, headers=admin).json()
    assert only_service["meta"]["total"] == 1
    assert client.get(f"{API}/products", params={"type": "gadget"}, headers=admin).status_code == 400


def test_seeded_product_is_listed_with_its_variant(client, admin):
    body = client.get(f"{API}/products", params={"q": "Brightloop CRM"}, headers=admin).json()
    crm = next(p for p in body["data"] if p["name"] == "Brightloop CRM")
    assert any(v["value"] == "Odoo" and v["extraPrice"] == "560.00" for v in crm["variants"])


def test_patch_is_partial_and_rejects_nulls(client, admin):
    p = _product(client, admin, notes="keep?", variants=[{"attribute": "Brand", "value": "Odoo", "extraPrice": "5.00"}])
    r = client.patch(f"{API}/products/{p['id']}", json={"salesPrice": "1200.00", "isActive": False}, headers=admin)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["salesPrice"] == "1200.00" and updated["isActive"] is False
    assert updated["costPrice"] == "400.00" and updated["notes"] == "keep?" and updated["name"] == p["name"]
    assert len(updated["variants"]) == 1
    assert client.patch(f"{API}/products/{p['id']}", json={"notes": None}, headers=admin).json()["notes"] is None
    assert client.patch(f"{API}/products/{p['id']}", json={"name": None}, headers=admin).status_code == 400
    assert client.patch(f"{API}/products/{MISSING_ID}", json={"name": "z"}, headers=admin).status_code == 404


def test_archive_is_soft_and_idempotent(client, admin):
    p = _product(client, admin)
    assert client.delete(f"{API}/products/{p['id']}", headers=admin).status_code == 204
    assert client.get(f"{API}/products/{p['id']}", headers=admin).json()["isActive"] is False
    assert client.delete(f"{API}/products/{p['id']}", headers=admin).status_code == 204
    assert client.delete(f"{API}/products/{MISSING_ID}", headers=admin).status_code == 404


def test_variant_crud(client, admin):
    p = _product(client, admin)
    url = f"{API}/products/{p['id']}/variants"
    created = client.post(url, json={"attribute": "Brand", "value": "Odoo", "extraPrice": "560.00"}, headers=admin)
    assert created.status_code == 201, created.text
    v = created.json()
    assert v["productId"] == p["id"] and v["isArchived"] is False

    dup = client.post(url, json={"attribute": "Brand", "value": "Odoo", "extraPrice": "1.00"}, headers=admin)
    assert dup.status_code == 409

    patched = client.patch(f"{url}/{v['id']}", json={"extraPrice": "600.00"}, headers=admin)
    assert patched.status_code == 200 and patched.json()["extraPrice"] == "600.00"
    assert patched.json()["value"] == "Odoo"

    other = client.post(url, json={"attribute": "Brand", "value": "Zoho", "extraPrice": "0.00"}, headers=admin).json()
    clash = client.patch(f"{url}/{other['id']}", json={"value": "Odoo"}, headers=admin)
    assert clash.status_code == 409

    assert client.delete(f"{url}/{v['id']}", headers=admin).status_code == 204
    remaining = client.get(f"{API}/products/{p['id']}", headers=admin).json()["variants"]
    assert [x["id"] for x in remaining] == [other["id"]]


def test_variant_must_belong_to_the_product(client, admin):
    a, b = _product(client, admin), _product(client, admin)
    v = client.post(
        f"{API}/products/{a['id']}/variants", json={"attribute": "A", "value": "B", "extraPrice": "0"}, headers=admin
    ).json()
    wrong = f"{API}/products/{b['id']}/variants/{v['id']}"
    assert client.patch(wrong, json={"value": "C"}, headers=admin).status_code == 404
    assert client.delete(wrong, headers=admin).status_code == 404
    missing_product = f"{API}/products/{MISSING_ID}/variants"
    assert client.post(missing_product, json={"attribute": "A", "value": "B", "extraPrice": "0"}, headers=admin).status_code == 404


def test_variant_used_by_a_template_is_archived_not_deleted(client, admin):
    p = _product(client, admin, variants=[{"attribute": "Brand", "value": "Odoo", "extraPrice": "560.00"}])
    variant_id = p["variants"][0]["id"]
    with engine.begin() as conn:
        plan_id = conn.execute(text("select id from plans limit 1")).scalar_one()
        template_id = conn.execute(
            text("insert into quotation_templates (name, plan_id, validity_days) values (:n, :p, 30) returning id"),
            {"n": f"{TEST_PREFIX}tpl", "p": plan_id},
        ).scalar_one()
        conn.execute(
            text(
                "insert into quotation_template_lines (template_id, product_id, variant_id, quantity) "
                "values (:t, :p, :v, 1)"
            ),
            {"t": template_id, "p": p["id"], "v": variant_id},
        )
    url = f"{API}/products/{p['id']}/variants/{variant_id}"
    assert client.delete(url, headers=admin).status_code == 204
    [v] = client.get(f"{API}/products/{p['id']}", headers=admin).json()["variants"]
    assert v["id"] == variant_id and v["isArchived"] is True
