"""
Tests for app/sources.py — mainly the per-user state fix. Before this
fix, the active data source was a single process-wide value, so two
signed-in users (or the same user in two tabs) would silently share and
overwrite each other's connection.
"""

import pytest

from app import database as demo_db
from app import sources


@pytest.fixture(autouse=True)
def isolated_demo_db(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_db, "DB_PATH", tmp_path / "demo.db")
    yield


class TestPerUserIsolation:
    def test_users_start_disconnected(self):
        assert sources.is_connected("alice") is False
        assert sources.is_connected("bob") is False

    def test_one_users_connection_does_not_affect_another(self):
        sources.connect_demo("alice")

        assert sources.is_connected("alice") is True
        assert sources.is_connected("bob") is False

    def test_disconnecting_one_user_does_not_affect_another(self):
        sources.connect_demo("alice")
        sources.connect_demo("bob")

        sources.disconnect("bob")

        assert sources.is_connected("alice") is True
        assert sources.is_connected("bob") is False

    def test_source_info_is_scoped_per_user(self):
        sources.connect_demo("alice")

        alice_info = sources.get_source_info("alice")
        bob_info = sources.get_source_info("bob")

        assert alice_info["connected"] is True
        assert alice_info["name"] == "RetailDB"
        assert bob_info["connected"] is False
        assert bob_info["name"] is None

    def test_dialect_defaults_to_sqlite_when_disconnected(self):
        # get_dialect() is called in a few places before checking
        # is_connected() — it should never raise, just fall back safely.
        assert sources.get_dialect("nobody") == "sqlite"


class TestConnectSqlitePathAllowlist:
    """connect_sqlite_path() lets a user type a filename and have the
    server open it — without a boundary that's an arbitrary local-file
    read primitive, so it's restricted to LOCAL_SOURCES_DIR only."""

    def _make_sqlite_file(self, path):
        import sqlite3
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()

    def test_file_inside_allowed_dir_connects(self, tmp_path, monkeypatch):
        allowed_dir = tmp_path / "local_sources"
        monkeypatch.setattr(sources, "LOCAL_SOURCES_DIR", allowed_dir)
        self._make_sqlite_file(allowed_dir / "mydata.db")

        info = sources.connect_sqlite_path("tester", "mydata.db")

        assert info["connected"] is True

    def test_absolute_path_is_rejected(self, tmp_path, monkeypatch):
        allowed_dir = tmp_path / "local_sources"
        monkeypatch.setattr(sources, "LOCAL_SOURCES_DIR", allowed_dir)
        outside_file = tmp_path / "outside" / "secret.db"
        self._make_sqlite_file(outside_file)

        with pytest.raises(sources.SourceError, match="absolute path"):
            sources.connect_sqlite_path("tester", str(outside_file))

    def test_path_traversal_is_rejected(self, tmp_path, monkeypatch):
        allowed_dir = tmp_path / "local_sources"
        monkeypatch.setattr(sources, "LOCAL_SOURCES_DIR", allowed_dir)
        outside_file = tmp_path / "outside" / "secret.db"
        self._make_sqlite_file(outside_file)

        with pytest.raises(sources.SourceError, match="outside it|absolute path"):
            sources.connect_sqlite_path("tester", "../outside/secret.db")

    def test_nonexistent_file_in_allowed_dir_gives_clean_error(self, tmp_path, monkeypatch):
        allowed_dir = tmp_path / "local_sources"
        monkeypatch.setattr(sources, "LOCAL_SOURCES_DIR", allowed_dir)

        with pytest.raises(sources.SourceError, match="No file found"):
            sources.connect_sqlite_path("tester", "nonexistent.db")


class TestForeignKeyExtraction:
    """get_schema_metadata() now reads real FK constraints (not just
    column names) — RetailDB's demo schema declares orders.customer_id
    -> customers.customer_id, order_items.order_id -> orders.order_id,
    and order_items.product_id -> products.product_id via REFERENCES
    clauses (see database.py's SCHEMA_SQL), so this is exercised against
    real SQLite foreign-key introspection, not a mock."""

    def test_every_table_has_a_foreign_keys_key(self):
        sources.connect_demo("kunal")
        tables = sources.get_schema_metadata("kunal")
        assert tables
        for t in tables:
            assert "foreign_keys" in t

    def test_orders_references_customers(self):
        sources.connect_demo("kunal")
        tables = {t["name"]: t for t in sources.get_schema_metadata("kunal")}

        fks = tables["orders"]["foreign_keys"]
        assert any(
            fk["column"] == "customer_id"
            and fk["references_table"] == "customers"
            and fk["references_column"] == "customer_id"
            for fk in fks
        )

    def test_order_items_references_both_orders_and_products(self):
        sources.connect_demo("kunal")
        tables = {t["name"]: t for t in sources.get_schema_metadata("kunal")}

        fks = tables["order_items"]["foreign_keys"]
        referenced_tables = {fk["references_table"] for fk in fks}
        assert referenced_tables == {"orders", "products"}

    def test_table_with_no_foreign_keys_gets_empty_list(self):
        sources.connect_demo("kunal")
        tables = {t["name"]: t for t in sources.get_schema_metadata("kunal")}

        assert tables["customers"]["foreign_keys"] == []
