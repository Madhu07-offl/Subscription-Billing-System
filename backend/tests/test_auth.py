import logging
import re

from sqlalchemy import text

from app.db import engine
from tests.conftest import auth_header, unique_email

API = "/api/v1"
ADMIN = {"email": "admin@brightloop.test", "password": "ChangeMe#2026"}  # from database/seed.sql


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}


# ------------------------------------------------------------------ login / me
def test_seeded_admin_can_login_and_read_me(client):
    r = client.post(f"{API}/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"token", "expiresIn", "user"}
    assert body["user"]["role"] == "admin"
    assert body["user"]["customerId"] is None

    me = client.get(f"{API}/auth/me", headers=auth_header(body["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN["email"]
    assert set(me.json()) == {"id", "name", "email", "role", "isActive", "customerId", "createdAt"}


def test_login_is_case_insensitive_on_email(client):
    r = client.post(f"{API}/auth/login", json={"email": "ADMIN@Brightloop.TEST", "password": ADMIN["password"]})
    assert r.status_code == 200


def test_login_wrong_password_and_unknown_email_are_identical_401(client):
    bad_pw = client.post(f"{API}/auth/login", json={**ADMIN, "password": "Wrong#Pass1"})
    unknown = client.post(f"{API}/auth/login", json={"email": unique_email("nobody"), "password": "Wrong#Pass1"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json() == unknown.json()
    assert bad_pw.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_requires_valid_token(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    r = client.get(f"{API}/auth/me", headers=auth_header("garbage"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_deactivated_user_gets_403(client, new_user):
    email, password, _ = new_user("inactive")
    with engine.begin() as conn:
        conn.execute(text("update users set is_active = false where email = :e"), {"e": email})
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    # an old token stops working too
    with engine.begin() as conn:
        conn.execute(text("update users set is_active = true where email = :e"), {"e": email})
    token = client.post(f"{API}/auth/login", json={"email": email, "password": password}).json()["token"]
    with engine.begin() as conn:
        conn.execute(text("update users set is_active = false where email = :e"), {"e": email})
    assert client.get(f"{API}/auth/me", headers=auth_header(token)).status_code == 403


# ---------------------------------------------------------------------- signup
def test_signup_creates_customer_user_and_logs_in(client):
    email = unique_email("signup").upper().replace("PYTEST", "pytest")  # mixed case on purpose
    r = client.post(
        f"{API}/auth/signup",
        json={"name": "Asha Test", "email": email, "password": "Brightloop#2026", "company": "Acme", "phone": "123"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "customer"
    assert body["user"]["customerId"] is not None
    assert body["user"]["email"] == email.lower()

    with engine.connect() as conn:
        row = conn.execute(
            text("select name, company, phone from customers where id = :i"), {"i": body["user"]["customerId"]}
        ).one()
    assert tuple(row) == ("Asha Test", "Acme", "123")
    assert client.get(f"{API}/auth/me", headers=auth_header(body["token"])).status_code == 200


def test_signup_duplicate_email_is_409_case_insensitive(client, new_user):
    email, _, _ = new_user("dup")
    r = client.post(f"{API}/auth/signup", json={"name": "X", "email": email.upper(), "password": "Brightloop#2026"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_signup_cannot_create_staff_or_admin(client):
    r = client.post(
        f"{API}/auth/signup",
        json={"name": "Sneaky", "email": unique_email("sneaky"), "password": "Brightloop#2026", "role": "admin"},
    )
    assert r.status_code == 201 and r.json()["user"]["role"] == "customer"


def test_signup_links_to_existing_customer_without_login(client):
    email = unique_email("linked")
    with engine.begin() as conn:
        cid = conn.execute(
            text("insert into customers (name, email, company) values ('Staff Made', :e, 'Keep Me Ltd') returning id"),
            {"e": email},
        ).scalar_one()
    r = client.post(
        f"{API}/auth/signup",
        json={"name": "Different Name", "email": email, "password": "Brightloop#2026", "company": "Ignored", "phone": "99"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["customerId"] == str(cid)
    with engine.connect() as conn:
        n = conn.execute(text("select count(*) from customers where email = :e"), {"e": email}).scalar_one()
        row = conn.execute(text("select name, company, phone from customers where id = :i"), {"i": cid}).one()
    assert n == 1  # no duplicate
    assert tuple(row) == ("Staff Made", "Keep Me Ltd", "99")  # staff data kept, blanks filled


def test_signup_password_rules_return_400_with_field_details(client):
    for pw, expect in [
        ("Short#1a", "more than 8"),
        ("nouppercase#1", "uppercase"),
        ("NOLOWERCASE#1", "lowercase"),
        ("NoSpecialChar1", "special"),
    ]:
        r = client.post(f"{API}/auth/signup", json={"name": "X", "email": unique_email("pw"), "password": pw})
        assert r.status_code == 400, pw
        err = r.json()["error"]
        assert err["code"] == "VALIDATION_ERROR" and err["message"] == "Invalid input"
        assert err["details"][0]["field"] == "password"
        assert expect in err["details"][0]["message"]


def test_signup_missing_fields_and_bad_email(client):
    r = client.post(f"{API}/auth/signup", json={"email": "not-an-email"})
    assert r.status_code == 400
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"name", "email", "password"} <= fields


def test_signup_blank_name_is_400(client):
    body = {"name": "   ", "email": unique_email("blank"), "password": "Brightloop#2026"}
    r = client.post(f"{API}/auth/signup", json=body)
    assert r.status_code == 400  # not a 500 from the database CHECK
    assert [d["field"] for d in r.json()["error"]["details"]] == ["name"]


# ------------------------------------------------------------- password reset
def test_forgot_password_always_202_and_logs_link(client, new_user, caplog):
    email, _, _ = new_user("forgot")
    with caplog.at_level(logging.INFO, logger="app.auth"):
        known = client.post(f"{API}/auth/forgot-password", json={"email": email})
        unknown = client.post(f"{API}/auth/forgot-password", json={"email": unique_email("ghost")})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()  # cannot probe which emails exist
    links = re.findall(r"reset-password\?token=(\S+)", caplog.text)
    assert len(links) == 1  # only the real account got a link

    with engine.connect() as conn:
        stored = conn.execute(
            text("select t.token_hash, t.expires_at - t.created_at from password_reset_tokens t join users u on u.id = t.user_id where u.email = :e"),
            {"e": email},
        ).one()
    assert stored[0] != links[0] and len(stored[0]) == 64  # hash only
    assert 29 * 60 <= stored[1].total_seconds() <= 31 * 60  # 30 minutes


def test_reset_password_flow_single_use(client, new_user, caplog):
    email, old_pw, _ = new_user("reset")
    with caplog.at_level(logging.INFO, logger="app.auth"):
        client.post(f"{API}/auth/forgot-password", json={"email": email})
    token = re.search(r"reset-password\?token=(\S+)", caplog.text).group(1)

    weak = client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "weak"})
    assert weak.status_code == 400 and weak.json()["error"]["details"][0]["field"] == "newPassword"

    ok = client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "BrandNew#Pass1"})
    assert ok.status_code == 200, ok.text
    assert client.post(f"{API}/auth/login", json={"email": email, "password": old_pw}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "BrandNew#Pass1"}).status_code == 200

    again = client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "Another#Pass1"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reset_password_rejects_unknown_and_expired_token(client, new_user, caplog):
    bad = client.post(f"{API}/auth/reset-password", json={"token": "nope", "newPassword": "BrandNew#Pass1"})
    assert bad.status_code == 400

    email, _, _ = new_user("expired")
    with caplog.at_level(logging.INFO, logger="app.auth"):
        client.post(f"{API}/auth/forgot-password", json={"email": email})
    token = re.search(r"reset-password\?token=(\S+)", caplog.text).group(1)
    with engine.begin() as conn:
        # expires_at > created_at is a DB rule, so move both back
        conn.execute(
            text(
                "update password_reset_tokens set created_at = now() - interval '2 hours', "
                "expires_at = now() - interval '1 hour' where user_id = (select id from users where email = :e)"
            ),
            {"e": email},
        )
    r = client.post(f"{API}/auth/reset-password", json={"token": token, "newPassword": "BrandNew#Pass1"})
    assert r.status_code == 400


# ------------------------------------------------------------ change password
def test_change_password(client, new_user):
    email, pw, signup = new_user("change")
    h = auth_header(signup["token"])
    wrong = client.post(f"{API}/auth/change-password", headers=h, json={"currentPassword": "Nope#Nope1", "newPassword": "BrandNew#Pass1"})
    assert wrong.status_code == 400 and wrong.json()["error"]["details"][0]["field"] == "currentPassword"
    weak = client.post(f"{API}/auth/change-password", headers=h, json={"currentPassword": pw, "newPassword": "weak"})
    assert weak.status_code == 400
    ok = client.post(f"{API}/auth/change-password", headers=h, json={"currentPassword": pw, "newPassword": "BrandNew#Pass1"})
    assert ok.status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "BrandNew#Pass1"}).status_code == 200
    assert client.post(f"{API}/auth/change-password", json={}).status_code == 401


# ------------------------------------------------------------------ patch me
def test_patch_me_updates_customer_profile(client, new_user):
    _, _, signup = new_user("profile")
    h = auth_header(signup["token"])
    r = client.patch(
        f"{API}/auth/me",
        headers=h,
        json={"name": "Renamed", "phone": "555", "company": "NewCo", "address": {"line1": "1 Main St", "postalCode": "560001"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    with engine.connect() as conn:
        row = conn.execute(
            text("select name, phone, company, address_line1, postal_code, city from customers where id = :i"),
            {"i": signup["user"]["customerId"]},
        ).one()
    assert tuple(row) == ("Renamed", "555", "NewCo", "1 Main St", "560001", None)

    # partial: untouched fields stay, null clears
    client.patch(f"{API}/auth/me", headers=h, json={"company": None, "address": {"city": "Pune"}})
    with engine.connect() as conn:
        row = conn.execute(
            text("select phone, company, address_line1, city from customers where id = :i"),
            {"i": signup["user"]["customerId"]},
        ).one()
    assert tuple(row) == ("555", None, "1 Main St", "Pune")

    assert client.patch(f"{API}/auth/me", headers=h, json={"name": "  "}).status_code == 400
    assert client.get(f"{API}/auth/me", headers=h).json()["name"] == "Renamed"


def test_patch_me_for_admin_only_changes_name(client):
    token = client.post(f"{API}/auth/login", json=ADMIN).json()["token"]
    h = auth_header(token)
    r = client.patch(f"{API}/auth/me", headers=h, json={"phone": "123", "company": "x"})
    assert r.status_code == 200 and r.json()["name"] == "Admin"
