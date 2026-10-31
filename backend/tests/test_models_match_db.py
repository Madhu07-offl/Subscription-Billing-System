"""The ORM must mirror the deployed tables exactly (names, nullability, key columns).
Reads the live schema through reflection; changing a model without a migration (or vice versa) fails here."""
import pytest
from sqlalchemy import inspect

import app.models  # noqa: F401
from app.db import Base, engine

EXPECTED_TABLES = {
    "customers", "users", "password_reset_tokens",
    "products", "product_variants", "plans", "taxes", "tax_product_types",
    "quotation_templates", "quotation_template_lines",
    "discounts", "discount_products", "discount_subscriptions", "discount_usages",
    "document_sequences", "subscriptions", "subscription_lines", "subscription_status_history",
    "billing_runs", "invoices", "invoice_lines", "payments",
}  # fmt: skip


def test_every_migration_table_is_mapped():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_columns_match_database(table):
    insp = inspect(engine)
    db_cols = {c["name"]: c for c in insp.get_columns(table)}
    model_cols = {c.name: c for c in Base.metadata.tables[table].columns}

    assert set(model_cols) == set(db_cols), (
        f"{table}: only in model {set(model_cols) - set(db_cols)}, only in DB {set(db_cols) - set(model_cols)}"
    )
    for name, col in model_cols.items():
        db_nullable = db_cols[name]["nullable"]
        model_nullable = col.nullable and not col.primary_key
        assert model_nullable == db_nullable, f"{table}.{name}: nullable model={model_nullable} db={db_nullable}"


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_primary_keys_match_database(table):
    db_pk = set(inspect(engine).get_pk_constraint(table)["constrained_columns"])
    model_pk = {c.name for c in Base.metadata.tables[table].primary_key.columns}
    assert model_pk == db_pk
