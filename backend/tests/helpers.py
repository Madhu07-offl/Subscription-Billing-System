"""Shared by the catalogue/people tests: ready-made auth headers for each role."""
from tests.conftest import auth_header, unique_email

API = "/api/v1"
ADMIN = {"email": "admin@brightloop.test", "password": "ChangeMe#2026"}  # from database/seed.sql
STAFF_PASSWORD = "Sup3r#Secret"
MISSING_ID = "00000000-0000-4000-8000-00000000dead"


def admin_headers(client) -> dict[str, str]:
    r = client.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return auth_header(r.json()["token"])


def make_staff(client, admin) -> tuple[str, dict[str, str]]:
    email = unique_email("staff")
    body = {"name": "Test Staff", "email": email, "password": STAFF_PASSWORD}
    r = client.post(f"{API}/users/staff", json=body, headers=admin)
    assert r.status_code == 201, r.text
    login = client.post(f"{API}/auth/login", json={"email": email, "password": STAFF_PASSWORD})
    assert login.status_code == 200, login.text
    return email, auth_header(login.json()["token"])
