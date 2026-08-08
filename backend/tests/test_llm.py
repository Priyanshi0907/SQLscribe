"""
Tests for app/llm.py — specifically _build_schema_context, the function
that broke when sources.py moved from a single global connection to
per-user state (get_schema_metadata gained a required `username`
argument, and this call site wasn't updated to match). No LLM call is
made here — that would need a real Groq API key and network access, so
it's out of scope for this suite (see README's Testing section) — this
covers the schema-fetching path that runs before every LLM call.
"""

import pytest

from app import database as demo_db
from app import llm, schema_meta, sources


@pytest.fixture(autouse=True)
def isolated_demo_db(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_db, "DB_PATH", tmp_path / "demo.db")
    yield


@pytest.fixture(autouse=True)
def isolated_schema_meta_db(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    schema_meta.init_schema_meta_db()
    yield


class TestBuildSchemaContext:
    def test_builds_schema_text_for_connected_user(self):
        sources.connect_demo("kunal")

        schema_text = llm._build_schema_context("kunal")

        assert "customers" in schema_text
        assert "orders" in schema_text
        assert "customer_id" in schema_text

    def test_raises_source_error_for_user_with_no_connection(self):
        # Regression guard for the missing-username bug: this must raise
        # sources.SourceError (a clean, expected failure), never a
        # TypeError from a missing positional argument.
        with pytest.raises(sources.SourceError):
            llm._build_schema_context("nobody_connected")

    def test_schema_is_scoped_to_the_requesting_users_own_connection(self):
        sources.connect_demo("kunal")
        # priya has never connected anything
        with pytest.raises(sources.SourceError):
            llm._build_schema_context("priya")
        # kunal's own schema is unaffected by priya's failed lookup
        assert "customers" in llm._build_schema_context("kunal")

    def test_includes_real_foreign_key_relationships(self):
        sources.connect_demo("kunal")

        schema_text = llm._build_schema_context("kunal")

        assert "Foreign key relationships" in schema_text
        assert "orders.customer_id -> customers.customer_id" in schema_text

    def test_includes_saved_table_descriptions_when_present(self):
        sources.connect_demo("kunal")
        schema_meta.save_generated(
            "kunal",
            "RetailDB",
            table_descriptions={"customers": "Registered shopper profiles."},
            column_descriptions={"customers": {"email": "Shopper primary email address."}},
        )

        schema_text = llm._build_schema_context("kunal")

        assert "Registered shopper profiles." in schema_text
        assert "* email: Shopper primary email address." in schema_text

    def test_degrades_gracefully_with_no_saved_descriptions(self):
        # A source no one has run description generation against yet
        # should produce the same bare-schema output as before this
        # feature existed — no crash, no empty "-- " suffix artifacts.
        sources.connect_demo("kunal")

        schema_text = llm._build_schema_context("kunal")

        assert "customers(" in schema_text
        assert " -- " not in schema_text.split("Foreign key relationships")[0]


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, **kwargs):
        return _FakeCompletion(self._content)


class _FakeChat:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


class _FakeGroqClient:
    def __init__(self, content):
        self.chat = _FakeChat(content)


class TestGenerateTableDescriptions:
    def test_parses_json_object_response(self, monkeypatch):
        sources.connect_demo("kunal")
        fake_response = (
            '{"tables": {"customers": "Stores customer profiles.", "products": "Product catalog."}, '
            '"columns": {"customers": {"email": "Customer email"}}}'
        )
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(fake_response))

        result = llm.generate_table_descriptions("kunal")

        assert result["tables"]["customers"] == "Stores customer profiles."
        assert result["columns"]["customers"]["email"] == "Customer email"

    def test_strips_markdown_fences_if_model_adds_them(self, monkeypatch):
        sources.connect_demo("kunal")
        fake_response = '```json\n{"tables": {"customers": "Stores customer profiles."}}\n```'
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(fake_response))

        result = llm.generate_table_descriptions("kunal")

        assert result["tables"]["customers"] == "Stores customer profiles."

    def test_drops_hallucinated_table_names_not_in_real_schema(self, monkeypatch):
        sources.connect_demo("kunal")
        fake_response = '{"tables": {"customers": "Real table.", "made_up_table": "Should be dropped."}}'
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(fake_response))

        result = llm.generate_table_descriptions("kunal")

        assert "customers" in result["tables"]
        assert "made_up_table" not in result["tables"]

    def test_invalid_json_raises_runtime_error(self, monkeypatch):
        sources.connect_demo("kunal")
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient("not json at all"))

        with pytest.raises(RuntimeError):
            llm.generate_table_descriptions("kunal")

    def test_no_tables_returns_empty_dict_without_calling_llm(self, monkeypatch):
        sources.connect_demo("kunal")

        def _boom():
            raise AssertionError("should not call the LLM client when there are no tables")

        monkeypatch.setattr(sources, "get_schema_metadata", lambda username: [])
        monkeypatch.setattr(llm, "_get_client", _boom)

        assert llm.generate_table_descriptions("kunal") == {"tables": {}, "columns": {}, "skipped_tables": []}

    def test_reconciles_foreign_key_column_descriptions_with_target(self, monkeypatch):
        sources.connect_demo("kunal")
        fake_response = (
            '{"tables": {"customers": "Profiles", "orders": "Orders"}, '
            '"columns": {"customers": {"customer_id": "Unique customer ID"}}}'
        )
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(fake_response))

        result = llm.generate_table_descriptions("kunal")

        # orders.customer_id is an FK referencing customers.customer_id — it should inherit the description
        assert result["columns"]["customers"]["customer_id"] == "Unique customer ID"
        assert result["columns"]["orders"]["customer_id"] == "Unique customer ID"

    def test_reconciliation_overwrites_even_a_plausible_independently_worded_fk_description(self, monkeypatch):
        # The important case: the model's own FK-column text isn't empty
        # and isn't one of the old "generic-looking" placeholder strings
        # — it's a specific-sounding, plausible sentence that still
        # doesn't match how the referenced column itself is described.
        # Reconciliation must overwrite it anyway, not just fill in gaps.
        sources.connect_demo("kunal")
        fake_response = (
            '{"tables": {"customers": "Profiles", "orders": "Orders"}, '
            '"columns": {'
            '"customers": {"customer_id": "The customer\'s own unique ID."}, '
            '"orders": {"customer_id": "Identifies which customer placed this particular order."}'
            '}}'
        )
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(fake_response))

        result = llm.generate_table_descriptions("kunal")

        assert result["columns"]["orders"]["customer_id"] == "The customer's own unique ID."
        assert result["columns"]["orders"]["customer_id"] == result["columns"]["customers"]["customer_id"]

    def test_schema_over_the_table_cap_reports_skipped_tables(self, monkeypatch):
        sources.connect_demo("kunal")
        fake_tables = [
            {"name": f"table_{i}", "row_count": 0,
             "columns": [{"name": "id", "type": "INTEGER", "pk": True}], "foreign_keys": []}
            for i in range(llm.MAX_DESCRIPTION_TABLES + 3)
        ]
        monkeypatch.setattr(sources, "get_schema_metadata", lambda username: fake_tables)
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient('{"tables": {}, "columns": {}}'))

        result = llm.generate_table_descriptions("kunal")

        assert len(result["skipped_tables"]) == 3
        assert result["skipped_tables"] == [
            f"table_{i}" for i in range(llm.MAX_DESCRIPTION_TABLES, llm.MAX_DESCRIPTION_TABLES + 3)
        ]

    def test_tables_within_the_cap_are_not_reported_as_skipped(self, monkeypatch):
        sources.connect_demo("kunal")  # RetailDB has 4 tables, well under the cap
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient('{"tables": {}, "columns": {}}'))

        result = llm.generate_table_descriptions("kunal")

        assert result["skipped_tables"] == []

