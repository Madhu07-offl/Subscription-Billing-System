import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import security
from app.core.deps import CurrentUser, require_roles
from app.core.errors import AppError, register_error_handlers
from app.core.pagination import PageParams, Pagination
from app.schemas.common import CamelModel, Money


@pytest.mark.parametrize(
    ("password", "ok"),
    [
        ("Brightloop#2026", True),
        ("Short#1a", False),  # 8 chars: must be MORE than 8
        ("Exactly#9", True),
        ("nouppercase#1", False),
        ("NOLOWERCASE#1", False),
        ("NoSpecialChar1", False),
        ("A#" + "a" * 80, False),  # over bcrypt's 72 bytes
    ],
)
def test_password_rule(password, ok):
    assert (security.password_problems(password) == []) is ok


def test_hash_and_verify_roundtrip():
    h = security.hash_password("Brightloop#2026")
    assert security.verify_password("Brightloop#2026", h)
    assert not security.verify_password("wrong", h)
    assert not security.verify_password("x", "not-a-hash")


def test_jwt_roundtrip_and_tamper():
    uid = uuid.uuid4()
    token, expires_in = security.create_access_token(uid, "staff")
    assert expires_in > 0
    assert security.decode_access_token(token) == uid
    with pytest.raises(AppError) as e:
        security.decode_access_token(token + "x")
    assert e.value.code == "UNAUTHENTICATED"


def test_reset_token_is_stored_hashed():
    raw, stored = security.new_reset_token()
    assert raw != stored and stored == security.hash_reset_token(raw)


def test_money_serialises_as_two_decimal_string():
    class M(CamelModel):
        sales_price: Money

    from decimal import Decimal

    assert M(sales_price=Decimal("560")).model_dump(mode="json", by_alias=True) == {"salesPrice": "560.00"}


def test_error_shape_and_rbac_dependency(client, new_user):
    """require_roles on a throw-away app: customers are refused (403), the shape matches API.md."""
    mini = FastAPI()
    register_error_handlers(mini)

    @mini.get("/admin-only")
    def admin_only(user=Depends(require_roles("admin"))):
        return {"ok": True}

    @mini.get("/page")
    def page(p: Pagination):
        return {"page": p.page, "limit": p.limit, "offset": p.offset}

    c = TestClient(mini)
    _, _, signup = new_user("rbac")
    token = signup["token"]
    assert c.get("/admin-only").status_code == 401
    r = c.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json() == {"error": {"code": "FORBIDDEN", "message": "You do not have access to this resource"}}

    assert c.get("/page?page=3&limit=10").json() == {"page": 3, "limit": 10, "offset": 20}
    bad = c.get("/page?limit=101")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert bad.json()["error"]["details"][0]["field"] == "limit"


def test_page_params_offset():
    assert PageParams(page=1, limit=20).offset == 0
    assert PageParams(page=4, limit=25).offset == 75


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "NOT_FOUND", "message": "Not found"}}


def test_current_user_type_exported():
    assert CurrentUser is not None
