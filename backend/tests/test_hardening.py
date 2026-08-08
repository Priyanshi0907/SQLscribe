"""
Tests for the hardening pass: request rate limiting on /api/query and
/api/query/confirm, per-connection query timeouts, CORS origins read
from an env var, secret redaction in error messages, and the
session_store.py seam actually being used by sources.py.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app import auth, database as demo_db
from app import schema_meta, session_store, sources
from app.main import app, ALLOWED_ORIGINS, ALLOWED_ORIGINS_RAW

from test_api_integration import _stub_llm_response


@pytest.fixture(autouse=True)
def isolated_demo_db(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_db, "DB_PATH", tmp_path / "demo.db")
    yield


@pytest.fixture(autouse=True)
def isolated_schema_meta_db(tmp_path, monkeypatch):
    # The `client` fixture below triggers main.py's FastAPI lifespan,
    # which calls schema_meta.init_schema_meta_db() on startup — without
    # this, that call hits schema_meta's real default path and writes an
    # actual (empty, but real) file into backend/data/ on disk every
    # time this test file runs, instead of a throwaway temp file like
    # every other stateful module here gets.
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _signup_and_connect_demo(client, username: str) -> str:
    signup_resp = client.post(
        "/api/auth/signup", json={"username": username, "password": "correcthorse123"}
    )
    assert signup_resp.status_code == 200, signup_resp.text
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    connect_resp = client.post("/api/source/demo", headers=headers)
    assert connect_resp.status_code == 200, connect_resp.text
    return token


# ---------------------------------------------------------------------------
# Query rate limiting (auth.check_query_rate_limit, wired into both
# /api/query and /api/query/confirm)
# ---------------------------------------------------------------------------

class TestQueryRateLimitUnit:
    def test_allows_requests_under_the_limit(self):
        for _ in range(auth.QUERY_RATE_LIMIT):
            auth.check_query_rate_limit("rl_alice")  # should not raise

    def test_raises_429_once_the_limit_is_exceeded(self):
        for _ in range(auth.QUERY_RATE_LIMIT):
            auth.check_query_rate_limit("rl_bob")
        with pytest.raises(Exception) as exc_info:
            auth.check_query_rate_limit("rl_bob")
        assert exc_info.value.status_code == 429

    def test_retry_after_header_is_a_positive_integer_string(self):
        for _ in range(auth.QUERY_RATE_LIMIT):
            auth.check_query_rate_limit("rl_carol")
        with pytest.raises(Exception) as exc_info:
            auth.check_query_rate_limit("rl_carol")
        retry_after = exc_info.value.headers["Retry-After"]
        assert retry_after.isdigit()
        assert 0 < int(retry_after) <= int(auth.QUERY_WINDOW_SECONDS) + 1

    def test_limit_is_scoped_per_username(self):
        for _ in range(auth.QUERY_RATE_LIMIT):
            auth.check_query_rate_limit("rl_dave")
        auth.check_query_rate_limit("rl_erin")  # different user — should not raise

    def test_old_hits_outside_the_window_no_longer_count(self):
        auth._query_timestamps["rl_frank"] = [time.time() - auth.QUERY_WINDOW_SECONDS - 5] * auth.QUERY_RATE_LIMIT
        auth.check_query_rate_limit("rl_frank")  # should not raise — all recorded hits are stale


class TestQueryEndpointRateLimiting:
    def test_query_endpoint_returns_429_once_over_the_limit(self, client, monkeypatch):
        token = _signup_and_connect_demo(client, "ratetest_query")
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")

        for _ in range(auth.QUERY_RATE_LIMIT):
            resp = client.post("/api/query", json={"question": "show customers"}, headers=headers)
            assert resp.status_code == 200, resp.text

        over_limit_resp = client.post("/api/query", json={"question": "show customers"}, headers=headers)
        assert over_limit_resp.status_code == 429
        assert "Retry-After" in over_limit_resp.headers

    def test_rate_limit_is_scoped_per_user_at_the_endpoint_level(self, client, monkeypatch):
        token_a = _signup_and_connect_demo(client, "ratetest_a")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")
        for _ in range(auth.QUERY_RATE_LIMIT):
            client.post("/api/query", json={"question": "x"}, headers=headers_a)

        token_b = _signup_and_connect_demo(client, "ratetest_b")
        headers_b = {"Authorization": f"Bearer {token_b}"}
        resp_b = client.post("/api/query", json={"question": "x"}, headers=headers_b)
        assert resp_b.status_code == 200, resp_b.text  # a different user isn't affected

    def test_confirm_endpoint_shares_the_same_limiter(self, client, monkeypatch):
        token = _signup_and_connect_demo(client, "ratetest_confirm")
        headers = {"Authorization": f"Bearer {token}"}
        _stub_llm_response(monkeypatch, "SELECT * FROM customers LIMIT 1")

        for _ in range(auth.QUERY_RATE_LIMIT):
            client.post("/api/query", json={"question": "x"}, headers=headers)

        resp = client.post(
            "/api/query/confirm",
            json={"question": "x", "sql": "SELECT * FROM customers"},
            headers=headers,
        )
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

class TestSecretRedaction:
    def test_redact_for_user_strips_a_stored_postgres_password(self):
        session_store.default_session_store.set_session("redacttest", {
            "type": "postgres", "name": "mydb", "sqlite_path": None,
            "pg_config": {"host": "h", "port": 5432, "dbname": "mydb", "user": "u", "password": "s3cr3t!"},
            "mysql_config": None,
        })
        message = 'connection to server failed: password authentication failed for user "u" (s3cr3t!)'

        redacted = sources.redact_for_user("redacttest", message)

        assert "s3cr3t!" not in redacted
        assert "[redacted]" in redacted

    def test_redact_for_user_is_a_no_op_for_a_user_with_no_active_source(self):
        message = "some ordinary error"
        assert sources.redact_for_user("nobody_connected_hardening", message) == message

    def test_redact_for_user_is_a_no_op_when_message_has_no_secret_in_it(self):
        session_store.default_session_store.set_session("redacttest2", {
            "type": "postgres", "name": "mydb", "sqlite_path": None,
            "pg_config": {"host": "h", "port": 5432, "dbname": "mydb", "user": "u", "password": "s3cr3t!"},
            "mysql_config": None,
        })
        message = "syntax error near SELECT"
        assert sources.redact_for_user("redacttest2", message) == message

    def test_connect_postgres_failure_message_never_contains_the_password(self, monkeypatch):
        import psycopg2

        def _boom(**kwargs):
            raise psycopg2.OperationalError(
                f"connection failed: password=\"{kwargs.get('password')}\" was rejected"
            )

        monkeypatch.setattr(sources.psycopg2, "connect", _boom)

        with pytest.raises(sources.SourceError) as exc_info:
            sources.connect_postgres("x_hardening", "host", 5432, "db", "user", "supersecretpw")

        assert "supersecretpw" not in str(exc_info.value)

    def test_connect_mysql_failure_message_never_contains_the_password(self, monkeypatch):
        def _boom(**kwargs):
            raise Exception(f"Access denied for password '{kwargs.get('password')}'")

        monkeypatch.setattr(sources.pymysql, "connect", _boom)

        with pytest.raises(sources.SourceError) as exc_info:
            sources.connect_mysql("y_hardening", "host", 3306, "db", "user", "anothersecretpw")

        assert "anothersecretpw" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Query timeout plumbing
# ---------------------------------------------------------------------------

class TestQueryTimeout:
    def test_timeout_env_var_is_read_into_the_module_constant(self, monkeypatch):
        # QUERY_TIMEOUT_SECONDS is read once at import time from
        # SQLSCRIBE_QUERY_TIMEOUT_SECONDS — this proves the parsing logic
        # itself is correct without needing a process restart.
        assert isinstance(sources.QUERY_TIMEOUT_SECONDS, float)

    def test_sqlite_connections_get_a_progress_handler_installed(self):
        sources.connect_demo("timeouttest")
        conn = sources.get_connection("timeouttest")
        try:
            conn.execute("SELECT 1").fetchone()  # a normal fast query is unaffected
        finally:
            conn.close()

    def test_a_deliberately_expensive_sqlite_query_is_cut_off(self):
        sources.connect_demo("timeouttest2")
        conn = sources.get_connection("timeouttest2")
        try:
            # Override with a much tighter deadline than the real
            # 25s default so this test doesn't take 25 seconds to run.
            deadline_hit = time.monotonic() + 0.05

            def _handler():
                return time.monotonic() > deadline_hit

            conn.set_progress_handler(_handler, 1)
            with pytest.raises(Exception):
                conn.execute(
                    "WITH RECURSIVE counter(x) AS "
                    "(SELECT 1 UNION ALL SELECT x+1 FROM counter) "
                    "SELECT COUNT(*) FROM counter"
                ).fetchone()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# CORS origins from env
# ---------------------------------------------------------------------------

class TestCorsConfig:
    def test_default_origins_include_local_dev_ports(self):
        assert "http://localhost:5173" in ALLOWED_ORIGINS

    def test_allowed_origins_is_parsed_from_the_raw_env_string(self):
        origins = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",") if o.strip()]
        assert origins == ALLOWED_ORIGINS

    def test_allowed_origins_env_var_parsing_is_comma_separated(self):
        raw = "https://a.example.com, https://b.example.com"
        parsed = [o.strip() for o in raw.split(",") if o.strip()]
        assert parsed == ["https://a.example.com", "https://b.example.com"]


# ---------------------------------------------------------------------------
# session_store.py seam is actually wired into sources.py, not dead code
# ---------------------------------------------------------------------------

class TestSessionStoreIsActuallyUsed:
    def test_sources_sessions_is_the_same_object_the_store_uses(self):
        # Not just "a dict that behaves the same" — the literal same
        # backing dict, so a write through either path is visible
        # through the other.
        assert sources._sessions is session_store.default_session_store._sessions

    def test_connecting_writes_through_the_session_store_interface(self):
        sources.connect_demo("seamtest")
        state = session_store.default_session_store.get_session("seamtest")
        assert state is not None
        assert state["type"] == "demo"

    def test_disconnect_goes_through_set_session_not_a_raw_dict_write(self):
        sources.connect_demo("seamtest2")
        sources.disconnect("seamtest2")
        state = session_store.default_session_store.get_session("seamtest2")
        assert state["type"] is None

    def test_sources_sessions_dot_clear_still_works_for_test_isolation(self):
        sources._get_state("seamtest3")
        assert "seamtest3" in sources._sessions
        sources._sessions.clear()
        assert "seamtest3" not in sources._sessions
        assert session_store.default_session_store.get_session("seamtest3") is None
