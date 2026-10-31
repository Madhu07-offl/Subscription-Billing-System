import pytest

from tests.conftest import auth_header, unique_email
from tests.helpers import API, MISSING_ID, STAFF_PASSWORD, admin_headers, make_staff


@pytest.fixture(scope="module")
def admin(client):
    return admin_headers(client)


def test_create_staff_then_login(client, admin):
    email = unique_email("staff")
    body = {"name": "Sam Staff", "email": email.upper(), "password": STAFF_PASSWORD}
    r = client.post(f"{API}/users/staff", json=body, headers=admin)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["role"] == "staff" and created["customerId"] is None and created["isActive"] is True
    assert created["email"] == email  # normalised to lowercase
    assert "passwordHash" not in created and "password" not in created
    assert client.post(f"{API}/auth/login", json={"email": email, "password": STAFF_PASSWORD}).status_code == 200


def test_create_staff_duplicate_email_is_409(client, admin):
    email, _ = make_staff(client, admin)
    body = {"name": "Dup", "email": email, "password": STAFF_PASSWORD}
    r = client.post(f"{API}/users/staff", json=body, headers=admin)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_create_staff_weak_password_is_400_with_field(client, admin):
    body = {"name": "Weak", "email": unique_email(), "password": "short"}
    r = client.post(f"{API}/users/staff", json=body, headers=admin)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["details"][0]["field"] == "password"


def test_blank_name_is_400(client, admin):
    body = {"name": "   ", "email": unique_email("staff"), "password": STAFF_PASSWORD}
    r = client.post(f"{API}/users/staff", json=body, headers=admin)
    assert r.status_code == 400  # not a 409: the email is free, the name is blank
    assert r.json()["error"]["details"][0]["field"] == "name"
    email, _ = make_staff(client, admin)
    [staff] = client.get(f"{API}/users", params={"q": email}, headers=admin).json()["data"]
    assert client.patch(f"{API}/users/{staff['id']}", json={"name": " "}, headers=admin).status_code == 400


def test_only_admin_may_manage_users(client, admin, new_user):
    _, staff = make_staff(client, admin)
    _, _, customer = new_user("cust")
    for headers in (staff, auth_header(customer["token"])):
        assert client.get(f"{API}/users", headers=headers).status_code == 403
        assert client.post(f"{API}/users/staff", json={}, headers=headers).status_code == 403
    assert client.get(f"{API}/users").status_code == 401


def test_list_filters_and_pagination(client, admin):
    email, _ = make_staff(client, admin)
    params = {"q": email, "role": "staff", "isActive": "true", "limit": 5}
    body = client.get(f"{API}/users", params=params, headers=admin).json()
    assert [u["email"] for u in body["data"]] == [email]
    assert body["meta"] == {"page": 1, "limit": 5, "total": 1, "totalPages": 1}
    assert client.get(f"{API}/users", params={"role": "bogus"}, headers=admin).status_code == 400
    assert client.get(f"{API}/users", params={"limit": 101}, headers=admin).status_code == 400


def test_get_user_and_unknown_id(client, admin):
    email, _ = make_staff(client, admin)
    user = client.get(f"{API}/users", params={"q": email}, headers=admin).json()["data"][0]
    assert client.get(f"{API}/users/{user['id']}", headers=admin).json()["email"] == email
    r = client.get(f"{API}/users/{MISSING_ID}", headers=admin)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert client.get(f"{API}/users/not-a-uuid", headers=admin).status_code == 400


def test_deactivate_blocks_login_and_reactivate_restores_it(client, admin):
    email, _ = make_staff(client, admin)
    credentials = {"email": email, "password": STAFF_PASSWORD}
    user = client.get(f"{API}/users", params={"q": email}, headers=admin).json()["data"][0]
    off = client.patch(f"{API}/users/{user['id']}", json={"isActive": False, "name": "Renamed"}, headers=admin)
    assert off.status_code == 200 and off.json()["isActive"] is False and off.json()["name"] == "Renamed"
    assert client.post(f"{API}/auth/login", json=credentials).status_code == 403
    on = client.patch(f"{API}/users/{user['id']}", json={"isActive": True}, headers=admin)
    assert on.json()["isActive"] is True and on.json()["name"] == "Renamed"
    assert client.post(f"{API}/auth/login", json=credentials).status_code == 200


def test_admin_cannot_deactivate_self(client, admin):
    me = client.get(f"{API}/auth/me", headers=admin).json()
    r = client.patch(f"{API}/users/{me['id']}", json={"isActive": False}, headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert client.get(f"{API}/auth/me", headers=admin).json()["isActive"] is True
