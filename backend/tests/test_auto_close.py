"""The daily auto-close job: active subscriptions past expiryDate on autoClose plans become closed."""
from datetime import timedelta

import pytest

from tests.support import API, TODAY, make_catalogue, make_customer, make_subscription


@pytest.fixture
def customer(client):
    return make_customer(client)


def expired(client, headers, customer, cat, days_ago: int = 5):
    """An active subscription whose expiryDate is `days_ago` days in the past."""
    return make_subscription(
        client, headers, customer, cat, start=TODAY - timedelta(days=days_ago + 30), expiry=TODAY - timedelta(days=days_ago)
    )


def auto_close(client, headers, **body):
    r = client.post(f"{API}/billing/auto-close", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def sub(client, headers, subscription_id):
    return client.get(f"{API}/subscriptions/{subscription_id}", headers=headers).json()


def test_closes_expired_subscriptions_on_auto_close_plans_and_writes_history(client, admin_headers, customer):
    cat = make_catalogue(auto_close=True)
    target = expired(client, admin_headers, customer, cat)
    assert target["status"] == "active" and target["nextBillingDate"] is not None

    result = auto_close(client, admin_headers)
    assert result["asOf"] == str(TODAY)
    assert result["closedCount"] == len(result["closed"]) >= 1
    assert {"subscriptionId": target["id"], "number": target["number"]} in result["closed"]

    closed = sub(client, admin_headers, target["id"])
    assert closed["status"] == "closed"
    assert closed["nextBillingDate"] is None
    assert closed["closedAt"] is not None
    assert closed["closeReason"] == f"Auto-closed: expired on {TODAY - timedelta(days=5)}"

    history = client.get(f"{API}/subscriptions/{target['id']}/history", headers=admin_headers).json()["data"]
    latest = history[0]
    assert (latest["event"], latest["fromStatus"], latest["toStatus"]) == ("status_change", "active", "closed")
    assert latest["changedBy"] is None  # automatic change
    assert latest["reason"] == closed["closeReason"]


def test_is_idempotent(client, admin_headers, customer):
    cat = make_catalogue(auto_close=True)
    target = expired(client, admin_headers, customer, cat)
    first = auto_close(client, admin_headers)
    assert target["id"] in {c["subscriptionId"] for c in first["closed"]}
    second = auto_close(client, admin_headers)
    assert target["id"] not in {c["subscriptionId"] for c in second["closed"]}
    history = client.get(f"{API}/subscriptions/{target['id']}/history", headers=admin_headers).json()["data"]
    assert [h["toStatus"] for h in history].count("closed") == 1


def test_leaves_alone_plans_without_autoclose_and_subscriptions_not_yet_expired(client, admin_headers, customer):
    manual = expired(client, admin_headers, customer, make_catalogue(auto_close=False))
    live = make_subscription(client, admin_headers, customer, make_catalogue(auto_close=True))  # expires in a year
    draft_like = make_subscription(
        client, admin_headers, customer, make_catalogue(auto_close=True), start=TODAY - timedelta(days=40),
        expiry=TODAY - timedelta(days=2), activate=False,
    )  # confirmed, never activated: only active subscriptions close

    result = auto_close(client, admin_headers)
    closed_ids = {c["subscriptionId"] for c in result["closed"]}
    assert not closed_ids & {manual["id"], live["id"], draft_like["id"]}
    assert sub(client, admin_headers, manual["id"])["status"] == "active"
    assert sub(client, admin_headers, live["id"])["status"] == "active"
    assert sub(client, admin_headers, draft_like["id"])["status"] == "confirmed"


def test_a_renewed_subscription_is_not_closed(client, admin_headers, customer):
    cat = make_catalogue(auto_close=True)
    target = expired(client, admin_headers, customer, cat)
    r = client.post(
        f"{API}/subscriptions/{target['id']}/renew", headers=admin_headers, json={"newExpiryDate": str(TODAY + timedelta(days=30))}
    )
    assert r.status_code == 200, r.text
    result = auto_close(client, admin_headers)
    assert target["id"] not in {c["subscriptionId"] for c in result["closed"]}
    assert sub(client, admin_headers, target["id"])["status"] == "active"


def test_is_admin_only(client, customer):
    assert client.post(f"{API}/billing/auto-close", headers=customer["headers"]).status_code == 403
    assert client.post(f"{API}/billing/auto-close").status_code == 401
