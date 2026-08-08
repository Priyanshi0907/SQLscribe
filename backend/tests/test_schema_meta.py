"""
Tests for app/schema_meta.py — the table-description "meta table" store.
"""

import pytest

from app import schema_meta


@pytest.fixture(autouse=True)
def isolated_schema_meta_db(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    schema_meta.init_schema_meta_db()
    yield


class TestSaveAndGet:
    def test_no_descriptions_returns_empty_dict(self):
        assert schema_meta.get_descriptions("kunal", "RetailDB") == {}

    def test_save_generated_round_trips(self):
        schema_meta.save_generated(
            "kunal", "RetailDB",
            table_descriptions={"customers": "Stores customer profiles.", "orders": "One row per order."},
            column_descriptions={"customers": {"email": "Customer contact email."}},
        )
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert result["customers"]["description"] == "Stores customer profiles."
        assert result["customers"]["is_custom"] is False
        assert result["customers"]["columns"]["email"]["description"] == "Customer contact email."
        assert result["customers"]["columns"]["email"]["is_custom"] is False
        assert result["orders"]["description"] == "One row per order."

    def test_scoped_per_user(self):
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "Kunal's description."})
        assert schema_meta.get_descriptions("priya", "RetailDB") == {}

    def test_scoped_per_database_name(self):
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "For RetailDB."})
        assert schema_meta.get_descriptions("kunal", "OtherDB") == {}

    def test_save_generated_upserts_on_rerun(self):
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "First draft."})
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "Regenerated draft."})
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert result["customers"]["description"] == "Regenerated draft."


class TestCustomDescriptions:
    def test_custom_description_is_flagged(self):
        schema_meta.set_custom_description("kunal", "RetailDB", "customers", "My own words.")
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert result["customers"]["description"] == "My own words."
        assert result["customers"]["is_custom"] is True

    def test_custom_column_description_is_flagged(self):
        schema_meta.set_custom_column_description("kunal", "RetailDB", "customers", "email", "User email address.")
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert result["customers"]["columns"]["email"]["description"] == "User email address."
        assert result["customers"]["columns"]["email"]["is_custom"] is True

    def test_generated_save_does_not_overwrite_custom_edit(self):
        schema_meta.set_custom_description("kunal", "RetailDB", "customers", "My own words.")
        schema_meta.set_custom_column_description("kunal", "RetailDB", "customers", "email", "My email desc.")
        schema_meta.save_generated(
            "kunal",
            "RetailDB",
            table_descriptions={"customers": "LLM would say this instead."},
            column_descriptions={"customers": {"email": "LLM email desc."}},
        )
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert result["customers"]["description"] == "My own words."
        assert result["customers"]["is_custom"] is True
        assert result["customers"]["columns"]["email"]["description"] == "My email desc."
        assert result["customers"]["columns"]["email"]["is_custom"] is True

    def test_clear_description_removes_it(self):
        schema_meta.set_custom_description("kunal", "RetailDB", "customers", "My own words.")
        schema_meta.clear_description("kunal", "RetailDB", "customers")
        assert schema_meta.get_descriptions("kunal", "RetailDB") == {}

    def test_clear_column_description_removes_it(self):
        schema_meta.set_custom_column_description("kunal", "RetailDB", "customers", "email", "My email desc.")
        schema_meta.clear_column_description("kunal", "RetailDB", "customers", "email")
        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert "email" not in result.get("customers", {}).get("columns", {})


class TestTruncateForSource:
    def test_truncate_keep_custom_removes_only_generated_rows(self):
        schema_meta.save_generated(
            "kunal",
            "RetailDB",
            table_descriptions={"customers": "Generated.", "orders": "Generated too."},
            column_descriptions={"customers": {"email": "Gen email."}},
        )
        schema_meta.set_custom_description("kunal", "RetailDB", "orders", "Manually written.")
        schema_meta.set_custom_column_description("kunal", "RetailDB", "orders", "total", "Manual total.")

        schema_meta.truncate_for_source("kunal", "RetailDB", keep_custom=True)

        result = schema_meta.get_descriptions("kunal", "RetailDB")
        assert "customers" not in result
        assert result["orders"]["description"] == "Manually written."
        assert result["orders"]["is_custom"] is True
        assert result["orders"]["columns"]["total"]["description"] == "Manual total."
        assert result["orders"]["columns"]["total"]["is_custom"] is True

    def test_truncate_without_keep_custom_removes_everything(self):
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "Generated."})
        schema_meta.set_custom_description("kunal", "RetailDB", "orders", "Manually written.")
        schema_meta.set_custom_column_description("kunal", "RetailDB", "orders", "total", "Manual total.")

        schema_meta.truncate_for_source("kunal", "RetailDB", keep_custom=False)

        assert schema_meta.get_descriptions("kunal", "RetailDB") == {}

    def test_truncate_does_not_affect_other_databases_or_users(self):
        schema_meta.save_generated("kunal", "RetailDB", {"customers": "For RetailDB."})
        schema_meta.save_generated("kunal", "OtherDB", {"widgets": "For OtherDB."})
        schema_meta.save_generated("priya", "RetailDB", {"customers": "Priya's own."})

        schema_meta.truncate_for_source("kunal", "RetailDB", keep_custom=False)

        assert schema_meta.get_descriptions("kunal", "RetailDB") == {}
        assert "widgets" in schema_meta.get_descriptions("kunal", "OtherDB")
        assert "customers" in schema_meta.get_descriptions("priya", "RetailDB")

