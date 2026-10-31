"""GET /invoices/{id}/print: the PDF shows the invoice and follows the same access rules as GET /invoices/{id}."""
import io
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from app.db import engine
from app.services.invoice_pdf import money
from tests.support import API, TODAY, make_catalogue, make_customer, make_subscription, run_billing

MISSING_ID = "00000000-0000-4000-8000-00000000dead"


@pytest.fixture
def cat():
    return make_catalogue()


@pytest.fixture
def customer(client):
    return make_customer(client)


def billed(client, headers, customer, cat, confirm=True) -> str:
    """Id of the first invoice of a fresh subscription, confirmed unless asked otherwise."""
    sub = make_subscription(client, headers, customer, cat)
    invoice_id = run_billing(client, headers, [sub["id"]])["created"][0]["id"]
    if confirm:
        assert client.post(f"{API}/invoices/{invoice_id}/confirm", headers=headers).status_code == 200
    return invoice_id


def pdf_text(response) -> str:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_pdf_shows_the_invoice_lines_totals_and_payments(client, admin_headers, cat, customer):
    invoice_id = billed(client, admin_headers, customer, cat)
    payment = {"invoiceId": invoice_id, "method": "upi", "amount": "500.00", "paymentDate": str(TODAY), "reference": "UTR-42"}
    assert client.post(f"{API}/payments", headers=admin_headers, json=payment).status_code == 201
    inv = client.get(f"{API}/invoices/{invoice_id}", headers=admin_headers).json()

    r = client.get(f"{API}/invoices/{invoice_id}/print", headers=admin_headers)
    content = pdf_text(r)
    assert r.headers["content-disposition"] == f'inline; filename="{inv["number"]}.pdf"'
    for expected in (
        inv["number"], inv["subscriptionNumber"], inv["customerDetails"]["name"], inv["customerDetails"]["email"],
        inv["lines"][0]["description"], "Confirmed", "UPI", "UTR-42",
        "1,716.00",  # total: 1560.00 + 10% tax
        "1,216.00",  # amount due after the 500.00 payment
    ):  # fmt: skip
        assert expected in content, expected


def test_customer_prints_only_own_issued_invoices(client, admin_headers, cat, customer):
    other = make_customer(client, "other")
    mine, theirs = billed(client, admin_headers, customer, cat), billed(client, admin_headers, other, cat)
    draft = billed(client, admin_headers, customer, cat, confirm=False)
    own = customer["headers"]

    assert client.get(f"{API}/invoices/{mine}/print", headers=own).status_code == 200
    assert client.get(f"{API}/invoices/{theirs}/print", headers=own).status_code == 404  # someone else's: 404, not 403
    assert client.get(f"{API}/invoices/{draft}/print", headers=own).status_code == 404  # customers never see drafts
    assert client.get(f"{API}/invoices/{MISSING_ID}/print", headers=admin_headers).status_code == 404
    assert client.get(f"{API}/invoices/{mine}/print").status_code == 401
    # staff see the draft, marked as such
    assert "DRAFT" in pdf_text(client.get(f"{API}/invoices/{draft}/print", headers=admin_headers))


def test_names_are_printed_literally(client, admin_headers, cat, customer):
    with engine.begin() as c:  # the invoice snapshots the customer when it is created
        c.execute(text("update customers set name = :n where id = :i"), {"n": "R&D <Labs> Pvt", "i": customer["id"]})
    invoice_id = billed(client, admin_headers, customer, cat)
    assert "R&D <Labs> Pvt" in pdf_text(client.get(f"{API}/invoices/{invoice_id}/print", headers=admin_headers))


@pytest.mark.parametrize(
    "value, shown",
    [("0", "0.00"), ("999.5", "999.50"), ("1000", "1,000.00"), ("100000", "1,00,000.00"), ("1234567.5", "12,34,567.50"),
     ("-2500", "-2,500.00")],
)  # fmt: skip
def test_money_uses_indian_grouping(value, shown):
    assert money(Decimal(value)) == shown
