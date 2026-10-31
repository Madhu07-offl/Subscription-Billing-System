import pytest

from tests.conftest import auth_header, unique_email
from tests.helpers import API, MISSING_ID, admin_headers, make_staff


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def _create(client, headers, **overrides):
    body = {"name": "Acme Ltd", "email": unique_email("cust"), **overrides}
    r = client.post(f"{API}/customers", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_returns_contract_shape(client, admin):
    c = _create(
        client,
        admin,
        company="Acme",
        phone="555-0100",
        taxId="GST123",
        address={"line1": "1 Main St", "city": "Pune", "postalCode": "411001", "country": "IN"},
    )
    assert set(c) == {
        "id", "name", "email", "phone", "company", "taxId", "address", "hasLogin", "activeSubscriptions", "createdAt"
    }
    assert c["hasLogin"] is False and c["activeSubscriptions"] == 0
    assert c["address"] == {
        "line1": "1 Main St", "line2": None, "city": "Pune", "state": None, "postalCode": "411001", "country": "IN"
    }
    assert client.get(f"{API}/customers/{c['id']}", headers=admin).json() == c


def test_duplicate_email_is_409_case_insensitive(client, admin):
    c = _create(client, admin)
    r = client.post(f"{API}/customers", json={"name": "Other", "email": c["email"].upper()}, headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_validation(client, admin):
    r = client.post(f"{API}/customers", json={"name": "", "email": "not-an-email"}, headers=admin)
    assert r.status_code == 400
    assert {d["field"] for d in r.json()["error"]["details"]} == {"name", "email"}


def test_staff_allowed_customer_forbidden(client, admin, new_user):
    _, staff = make_staff(client, admin)
    assert client.get(f"{API}/customers", headers=staff).status_code == 200
    _create(client, staff)
    _, _, signed_up = new_user("portal")
    assert client.get(f"{API}/customers", headers=auth_header(signed_up["token"])).status_code == 403
    assert client.get(f"{API}/customers").status_code == 401


def test_signed_up_customer_has_login(client, admin, new_user):
    email, _, signed_up = new_user("portal")
    found = client.get(f"{API}/customers", params={"q": email}, headers=admin).json()["data"]
    assert len(found) == 1 and found[0]["hasLogin"] is True
    assert found[0]["id"] == signed_up["user"]["customerId"]


def test_search_by_company_and_pagination(client, admin):
    tag = unique_email("q").split("@")[0]
    for i in range(3):
        _create(client, admin, name=f"Zed {i}", email=f"{tag}-{i}@example.com", company=f"Co {tag}")
    by_company = client.get(f"{API}/customers", params={"q": f"Co {tag}", "limit": 2}, headers=admin).json()
    assert by_company["meta"] == {"page": 1, "limit": 2, "total": 3, "totalPages": 2}
    assert len(by_company["data"]) == 2
    page2 = client.get(f"{API}/customers", params={"q": tag, "limit": 2, "page": 2}, headers=admin).json()
    assert len(page2["data"]) == 1


def test_get_unknown_is_404(client, admin):
    assert client.get(f"{API}/customers/{MISSING_ID}", headers=admin).status_code == 404


def test_patch_is_partial(client, admin):
    c = _create(client, admin, phone="111", company="Old Co", address={"city": "Pune", "country": "IN"})
    body = {"company": "New Co", "address": {"city": "Mumbai"}}
    r = client.patch(f"{API}/customers/{c['id']}", json=body, headers=admin)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["company"] == "New Co" and updated["phone"] == "111" and updated["name"] == c["name"]
    assert updated["address"]["city"] == "Mumbai" and updated["address"]["country"] == "IN"  # untouched keys survive
    cleared = client.patch(f"{API}/customers/{c['id']}", json={"phone": None}, headers=admin).json()
    assert cleared["phone"] is None


def test_patch_email_conflict_and_null_name(client, admin):
    a, b = _create(client, admin), _create(client, admin)
    assert client.patch(f"{API}/customers/{b['id']}", json={"email": a["email"]}, headers=admin).status_code == 409
    own = client.patch(f"{API}/customers/{b['id']}", json={"email": b["email"].upper()}, headers=admin)
    assert own.status_code == 200  # re-sending its own email is not a conflict
    assert client.patch(f"{API}/customers/{b['id']}", json={"name": None}, headers=admin).status_code == 400
