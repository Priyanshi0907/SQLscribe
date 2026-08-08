"""
Shared pytest fixtures.

Every test gets its own throwaway auth.db / history.db / schema_meta.db
(via tmp_path), and in-memory module state (sources._sessions,
auth._failed_attempts, auth._query_timestamps) is reset before each test
so tests can't leak state into one another regardless of run order.

schema_meta isolation lives here at the conftest level (not just in the
individual test files that happen to use TestClient(app)) after a real
bug: test_hardening.py's TestClient(app) fixture triggers main.py's
FastAPI lifespan, which calls schema_meta.init_schema_meta_db() on
startup — without isolating that path, every run of that file was
writing an actual (empty, but real) file into backend/data/ on disk.
Putting the fixture here means any *future* test file that spins up
TestClient(app) gets this for free, instead of relying on every author
remembering to add it themselves the way test_hardening.py didn't.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import auth, history, schema_meta, sources


@pytest.fixture(autouse=True)
def isolated_databases(tmp_path, monkeypatch):
    """Point auth.db, history.db, and schema_meta.db at a fresh temp
    file per test, and clear the in-memory per-user state these modules
    keep alongside their on-disk tables."""
    monkeypatch.setattr(auth, "AUTH_DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(history, "HISTORY_DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    auth.init_auth_db()
    history.init_history_db()

    auth._failed_attempts.clear()
    sources._sessions.clear()
    # Without this, a username reused across many test functions (very
    # common — "kunal", "alice", etc.) could accumulate hits against the
    # module-level query rate limiter across the whole test session and
    # start failing unrelated tests with a 429 that has nothing to do
    # with what that particular test is checking.
    auth._query_timestamps.clear()

    yield

    auth._failed_attempts.clear()
    sources._sessions.clear()
    auth._query_timestamps.clear()
