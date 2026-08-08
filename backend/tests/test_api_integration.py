"""
End-to-end integration tests through the real FastAPI app — signup,
connect a data source, ask a question, get SQL back, confirm a write.

Only the actual outbound network call to Groq is stubbed (via
llm._get_client); everything else runs for real: FastAPI routing,
auth, per-user session lookup, schema introspection, sql_guard
validation, and SQLite execution.

This is deliberately the level that would have caught the regression
where sources.get_schema_metadata() gained a required `username`
argument but llm.py's call to it wasn't updated to match — a test that
only calls llm.generate_sql() directly with a mocked HTTP response
would skip right past that bug, because the bug was in the *real* code
path (_build_schema_context) that runs before the network call is ever
made. Stubbing at the network boundary instead of the function boundary
is what keeps that path genuinely exercised.
"""

import pytest
from fastapi.testclient import TestClient

from app import database as demo_db
from app import llm, schema_meta
from app.main import app


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
    """Stands in for the real Groq SDK client. Only the network
    boundary is faked — generate_sql(), _build_schema_context(), and
    everything else in llm.py runs unmodified."""

    def __init__(self, content):
        self.chat = _FakeChat(content)


def _stub_llm_response(monkeypatch, sql_text: str):
    monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient(sql_text))


@pytest.fixture(autouse=True)
def isolated_demo_db(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_db, "DB_PATH", tmp_path / "demo.db")
    yield


@pytest.fixture(autouse=True)
def isolated_schema_meta_db(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _signup_and_connect_demo(client) -> str:
    signup_resp = client.post(
        "/api/auth/signup", json={"username": "kunal", "password": "correcthorse123"}
    )
    assert signup_resp.status_code == 200, signup_resp.text
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    connect_resp = client.post("/api/source/demo", headers=headers)
    assert connect_resp.status_code == 200, connect_resp.text

    return token


class TestQueryEndToEnd:
    def test_select_query_runs_immediately(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 5")

        resp = client.post(
            "/api/query", json={"question": "show me some customers"}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pending_confirmation"] is False
        assert data["read_only"] is True
        assert "customer_id" in data["columns"]
        assert data["row_count"] > 0

    def test_write_query_pauses_for_confirmation_and_does_not_execute(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(
            monkeypatch, "DELETE FROM customers WHERE customer_id = 1"
        )

        resp = client.post(
            "/api/query", json={"question": "delete customer 1"}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pending_confirmation"] is True
        assert data["row_count"] == 0  # nothing has run yet

        # Prove it really didn't execute: the row should still be there.
        _stub_llm_response(monkeypatch, "SELECT * FROM customers WHERE customer_id = 1")
        check = client.post(
            "/api/query", json={"question": "is customer 1 still there"}, headers=headers
        )
        assert check.json()["row_count"] == 1

    def test_confirming_a_write_actually_executes_it(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "DELETE FROM customers WHERE customer_id = 1")

        gen_resp = client.post(
            "/api/query", json={"question": "delete customer 1"}, headers=headers
        )
        sql_to_confirm = gen_resp.json()["sql"]

        confirm_resp = client.post(
            "/api/query/confirm",
            json={"question": "delete customer 1", "sql": sql_to_confirm},
            headers=headers,
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        assert confirm_resp.json()["pending_confirmation"] is False

        _stub_llm_response(monkeypatch, "SELECT * FROM customers WHERE customer_id = 1")
        check = client.post(
            "/api/query", json={"question": "is customer 1 still there"}, headers=headers
        )
        assert check.json()["row_count"] == 0  # actually deleted now

    def test_unqualified_delete_is_rejected_before_reaching_confirmation(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "DELETE FROM customers")  # no WHERE

        resp = client.post(
            "/api/query", json={"question": "delete all customers"}, headers=headers
        )

        assert resp.status_code == 422
        assert "WHERE clause" in resp.json()["detail"]

    def test_query_without_a_connected_source_is_rejected(self, client, monkeypatch):
        signup_resp = client.post(
            "/api/auth/signup", json={"username": "nodb", "password": "correcthorse123"}
        )
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/query", json={"question": "anything"}, headers=headers)

        assert resp.status_code == 400

    def test_query_without_auth_is_rejected(self, client):
        resp = client.post("/api/query", json={"question": "anything"})
        assert resp.status_code == 401


class TestHistoryEndToEnd:
    def test_query_shows_up_in_the_calling_users_history(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")

        client.post("/api/query", json={"question": "one customer please"}, headers=headers)

        history_resp = client.get("/api/history", headers=headers)
        questions = [h["question"] for h in history_resp.json()["history"]]
        assert "one customer please" in questions

    def test_second_user_does_not_see_first_users_history(self, client, monkeypatch):
        token_a = _signup_and_connect_demo(client)
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")
        client.post(
            "/api/query",
            json={"question": "alice's private question"},
            headers={"Authorization": f"Bearer {token_a}"},
        )

        signup_b = client.post(
            "/api/auth/signup", json={"username": "priya", "password": "correcthorse123"}
        )
        token_b = signup_b.json()["token"]

        history_b = client.get(
            "/api/history", headers={"Authorization": f"Bearer {token_b}"}
        )
        questions_b = [h["question"] for h in history_b.json()["history"]]
        assert "alice's private question" not in questions_b


class TestTableDescriptionsEndToEnd:
    """The 'meta table' feature: generate LLM descriptions for the active
    schema in one batched call, view them, and edit them by hand. Only
    the outbound Groq call is stubbed — routing, auth, schema_meta
    storage, and the truncate-then-refill regeneration logic all run for
    real."""

    _FAKE_DESCRIPTIONS_JSON = (
        '{"customers": "Stores registered customer profiles and contact info.", '
        '"products": "Product catalog with pricing and stock levels.", '
        '"orders": "One row per customer purchase transaction.", '
        '"order_items": "Line items belonging to an order, one row per product in the order."}'
    )

    def test_no_descriptions_before_generation(self, client):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get("/api/schema/descriptions", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["descriptions"] == {}

    def test_generate_populates_descriptions_for_every_table(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, self._FAKE_DESCRIPTIONS_JSON)

        resp = client.post("/api/schema/descriptions/generate", headers=headers)

        assert resp.status_code == 200, resp.text
        descriptions = resp.json()["descriptions"]
        assert descriptions["customers"]["description"].startswith("Stores registered")
        assert descriptions["customers"]["is_custom"] is False
        assert set(descriptions.keys()) == {"customers", "products", "orders", "order_items"}

    def test_generated_descriptions_persist_and_are_fetchable(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, self._FAKE_DESCRIPTIONS_JSON)
        client.post("/api/schema/descriptions/generate", headers=headers)

        resp = client.get("/api/schema/descriptions", headers=headers)

        assert resp.json()["descriptions"]["orders"]["description"] == (
            "One row per customer purchase transaction."
        )

    def test_manual_edit_overrides_and_survives_regeneration(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, self._FAKE_DESCRIPTIONS_JSON)
        client.post("/api/schema/descriptions/generate", headers=headers)

        edit_resp = client.put(
            "/api/schema/descriptions/orders",
            json={"description": "My own hand-written description."},
            headers=headers,
        )
        assert edit_resp.status_code == 200, edit_resp.text
        assert edit_resp.json()["descriptions"]["orders"]["is_custom"] is True

        # Regenerate — the custom edit on `orders` must survive by default
        regen_resp = client.post("/api/schema/descriptions/generate", headers=headers)
        descriptions = regen_resp.json()["descriptions"]
        assert descriptions["orders"]["description"] == "My own hand-written description."
        assert descriptions["orders"]["is_custom"] is True
        assert descriptions["customers"]["is_custom"] is False

        # Regenerate with overwrite_custom=true — resets custom edit back to fresh generated text
        overwrite_resp = client.post("/api/schema/descriptions/generate?overwrite_custom=true", headers=headers)
        overwrite_descs = overwrite_resp.json()["descriptions"]
        assert overwrite_descs["orders"]["description"] == "One row per customer purchase transaction."
        assert overwrite_descs["orders"]["is_custom"] is False

    def test_editing_unknown_table_is_rejected(self, client):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.put(
            "/api/schema/descriptions/not_a_real_table",
            json={"description": "Anything."},
            headers=headers,
        )

        assert resp.status_code == 404

    def test_delete_description_removes_it(self, client, monkeypatch):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.put(
            "/api/schema/descriptions/customers",
            json={"description": "Temporary."},
            headers=headers,
        )

        del_resp = client.delete("/api/schema/descriptions/customers", headers=headers)

        assert del_resp.status_code == 200, del_resp.text
        assert "customers" not in del_resp.json()["descriptions"]

    def test_descriptions_endpoints_require_a_connected_source(self, client):
        signup_resp = client.post(
            "/api/auth/signup", json={"username": "nodb2", "password": "correcthorse123"}
        )
        token = signup_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/schema/descriptions", headers=headers).status_code == 400
        assert client.post("/api/schema/descriptions/generate", headers=headers).status_code == 400

    def test_descriptions_require_auth(self, client):
        resp = client.get("/api/schema/descriptions")
        assert resp.status_code == 401

    def test_generated_descriptions_are_scoped_per_user(self, client, monkeypatch):
        token_a = _signup_and_connect_demo(client)
        _stub_llm_response(monkeypatch, self._FAKE_DESCRIPTIONS_JSON)
        client.post(
            "/api/schema/descriptions/generate",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        signup_b = client.post(
            "/api/auth/signup", json={"username": "priya2", "password": "correcthorse123"}
        )
        token_b = signup_b.json()["token"]
        client.post("/api/source/demo", headers={"Authorization": f"Bearer {token_b}"})

        resp_b = client.get(
            "/api/schema/descriptions", headers={"Authorization": f"Bearer {token_b}"}
        )
        assert resp_b.json()["descriptions"] == {}

    def test_llm_generated_descriptions_flow_into_query_prompt_context(self, client, monkeypatch):
        """End-to-end proof that generated descriptions actually reach
        the SQL-generation prompt, not just the descriptions endpoint —
        exercises _build_schema_context's read of schema_meta for real."""
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, self._FAKE_DESCRIPTIONS_JSON)
        client.post("/api/schema/descriptions/generate", headers=headers)

        captured = {}
        original_build = llm._build_schema_context

        def _spy(username):
            text = original_build(username)
            captured["schema_text"] = text
            return text

        monkeypatch.setattr(llm, "_build_schema_context", _spy)
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")

        client.post("/api/query", json={"question": "show a customer"}, headers=headers)

        assert "Stores registered customer profiles" in captured["schema_text"]
        assert "orders.customer_id -> customers.customer_id" in captured["schema_text"]

    def test_manual_column_edit_and_delete(self, client):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}

        edit_resp = client.put(
            "/api/schema/descriptions/customers/columns/email",
            json={"description": "Primary user email."},
            headers=headers,
        )
        assert edit_resp.status_code == 200, edit_resp.text
        col_desc = edit_resp.json()["descriptions"]["customers"]["columns"]["email"]
        assert col_desc["description"] == "Primary user email."
        assert col_desc["is_custom"] is True

        del_resp = client.delete(
            "/api/schema/descriptions/customers/columns/email",
            headers=headers,
        )
        assert del_resp.status_code == 200, del_resp.text
        assert "email" not in del_resp.json()["descriptions"].get("customers", {}).get("columns", {})

    def test_editing_unknown_column_is_rejected(self, client):
        token = _signup_and_connect_demo(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.put(
            "/api/schema/descriptions/customers/columns/not_a_real_col",
            json={"description": "Invalid column."},
            headers=headers,
        )
        assert resp.status_code == 404

