"""Tests run against the database in backend/.env (DATABASE_URL). Everything they create uses an
email starting with TEST_PREFIX and is deleted afterwards, so use a development database."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import engine
from app.main import app

TEST_PREFIX = "pytest-"


def unique_email(label: str = "user") -> str:
    return f"{TEST_PREFIX}{label}-{uuid.uuid4().hex[:10]}@example.com"


# Billing runs created through the API; the tests register their ids so cleanup can remove them too.
TRACKED_RUNS: set[str] = set()


def _cleanup() -> None:
    with engine.begin() as conn:
        pattern = {"p": f"{TEST_PREFIX}%"}
        mine = "select id from customers where email like :p"
        # Money first: payments and invoices (lines and discount usages cascade) of test customers, then the
        # billing runs the tests started. Subscriptions are RESTRICTed by invoices, so they come after.
        conn.execute(
            text(f"delete from payments where invoice_id in (select id from invoices where customer_id in ({mine}))"),
            pattern,
        )
        conn.execute(text(f"delete from invoices where customer_id in ({mine})"), pattern)
        if TRACKED_RUNS:
            conn.execute(text("delete from billing_runs where id = any(cast(:ids as uuid[]))"), {"ids": list(TRACKED_RUNS)})
        # Subscriptions (lines and history cascade) and catalogue rows made by tests; children before parents.
        conn.execute(text(f"delete from subscriptions where customer_id in ({mine})"), pattern)
        for table in ("discounts", "quotation_templates", "plans", "products", "taxes"):
            conn.execute(text(f"delete from {table} where name like :p"), pattern)
        # password_reset_tokens go with their users (ON DELETE CASCADE); users reference customers.
        conn.execute(text("delete from users where email like :p"), pattern)
        conn.execute(text("delete from customers where email like :p"), pattern)


@pytest.fixture(scope="session", autouse=True)
def _clean_test_rows():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def new_user(client):
    """Signs up a fresh customer; returns (email, password, signup response json)."""

    def make(label: str = "user"):
        email, password = unique_email(label), "Sup3r#Secret"
        r = client.post("/api/v1/auth/signup", json={"name": "Test User", "email": email, "password": password})
        assert r.status_code == 201, r.text
        return email, password, r.json()

    return make


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@brightloop.test", "password": "ChangeMe#2026"})
    assert r.status_code == 200, r.text
    return auth_header(r.json()["token"])
