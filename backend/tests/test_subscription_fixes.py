"""Fixes from the PR #4 review by Prakash: resume/close/activate edge cases."""
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.db import engine
from tests.support import API, TODAY, make_catalogue, make_customer, make_subscription


@pytest.fixture
def customer(client):
    return make_customer(client)


def act(client, headers, sub_id, action, **kwargs):
    return client.post(f"{API}/subscriptions/{sub_id}/{action}", headers=headers, **kwargs)


def get(client, headers, sub_id):
    return client.get(f"{API}/subscriptions/{sub_id}", headers=headers).json()


def test_a_closed_subscription_cannot_be_resumed(client, admin_headers, customer):
    sub = make_subscription(client, admin_headers, customer, make_catalogue())
    assert act(client, admin_headers, sub["id"], "pause").status_code == 200
    assert act(client, admin_headers, sub["id"], "close", json={}).status_code == 200

    r = act(client, admin_headers, sub["id"], "resume")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    closed = get(client, admin_headers, sub["id"])
    assert closed["status"] == "closed" and closed["nextBillingDate"] is None  # nothing came back to life


def test_closing_clears_the_paused_flag(client, admin_headers, customer):
    sub = make_subscription(client, admin_headers, customer, make_catalogue())
    act(client, admin_headers, sub["id"], "pause")
    assert get(client, admin_headers, sub["id"])["isPaused"] is True
    r = act(client, admin_headers, sub["id"], "close", json={"reason": "bye"})
    assert r.status_code == 200 and r.json()["isPaused"] is False


def test_auto_close_clears_the_paused_flag(client, admin_headers, customer):
    sub = make_subscription(
        client, admin_headers, customer, make_catalogue(auto_close=True),
        start=TODAY - timedelta(days=40), expiry=TODAY - timedelta(days=5),
    )
    act(client, admin_headers, sub["id"], "pause")
    r = client.post(f"{API}/billing/auto-close", headers=admin_headers, json={})
    assert sub["id"] in {c["subscriptionId"] for c in r.json()["closed"]}
    closed = get(client, admin_headers, sub["id"])
    assert (closed["status"], closed["isPaused"]) == ("closed", False)
    assert act(client, admin_headers, sub["id"], "resume").status_code == 409


def test_activate_rechecks_the_plan(client, admin_headers, customer):
    cat = make_catalogue()
    sub = make_subscription(client, admin_headers, customer, cat, activate=False)
    with engine.begin() as c:
        c.execute(text("update plans set is_active = false where id = :p"), {"p": cat["plan"]})
    r = act(client, admin_headers, sub["id"], "activate")
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUSINESS_RULE"
    assert "not active" in r.json()["error"]["message"]
    assert get(client, admin_headers, sub["id"])["status"] == "confirmed"


def test_activate_rechecks_the_plan_window_and_quantity(client, admin_headers, customer):
    cat = make_catalogue()
    sub = make_subscription(client, admin_headers, customer, cat, activate=False)
    with engine.begin() as c:  # plan now starts after the subscription does, and wants at least 5 per line
        c.execute(
            text("update plans set available_from = :f, min_quantity = 5 where id = :p"),
            {"f": TODAY + timedelta(days=30), "p": cat["plan"]},
        )
    r = act(client, admin_headers, sub["id"], "activate")
    assert r.status_code == 422
    assert len(r.json()["error"]["details"]) == 2


def test_activate_rechecks_the_dates(client, admin_headers, customer):
    sub = make_subscription(client, admin_headers, customer, make_catalogue(), activate=False)
    with engine.begin() as c:
        c.execute(text("update subscriptions set expiry_date = start_date where id = :i"), {"i": sub["id"]})
    r = act(client, admin_headers, sub["id"], "activate")
    assert r.status_code == 422 and "expiryDate" in r.json()["error"]["message"]


def test_activate_still_works_for_a_valid_subscription(client, admin_headers, customer):
    sub = make_subscription(client, admin_headers, customer, make_catalogue())
    assert sub["status"] == "active" and sub["nextBillingDate"] == str(TODAY)
