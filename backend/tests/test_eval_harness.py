"""
Tests for evals/eval_sql.py — not testing the model (that needs a real
Groq API key and network access, see the harness's own docstring/README
for how to run it for real), but proving the harness's own plumbing
actually works: it used to crash immediately with an ImportError
(`from app.sources import RETAIL_DB_PATH`, a name that never existed)
before ever reaching a single question, and even after that a second,
deeper bug meant every call would have failed with "No data source
connected yet." because the harness never registered its eval user with
sources.py.

These tests stub the LLM client the same way test_api_integration.py
does, so the whole real path (connect_demo -> generate_sql ->
_build_schema_context -> sql_guard.validate_sql -> real SQLite
execution -> row comparison) runs unmodified except for the actual
outbound network call.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database as demo_db
from app import llm, schema_meta

from test_api_integration import _FakeGroqClient

from evals.eval_sql import run_eval, BENCHMARK_QUESTIONS


@pytest.fixture(autouse=True)
def isolated_demo_db(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_db, "DB_PATH", tmp_path / "demo.db")
    yield


@pytest.fixture(autouse=True)
def isolated_schema_meta_db(tmp_path, monkeypatch):
    # generate_sql() -> _build_schema_context() reads from schema_meta.py
    # (a separate SQLite file from the demo database) to fold in any
    # saved table/column descriptions. Without this fixture, every call
    # here would hit whatever schema_meta.SCHEMA_META_DB_PATH happens to
    # point at on the real filesystem — uninitialized in a clean
    # checkout, which fails with "no such table: table_descriptions"
    # instead of the empty-but-valid state a fresh eval run should see.
    monkeypatch.setattr(schema_meta, "SCHEMA_META_DB_PATH", tmp_path / "schema_meta.db")
    schema_meta.init_schema_meta_db()
    yield


class TestEvalHarnessPlumbing:
    def test_run_eval_does_not_crash_on_import_or_missing_connection(self, monkeypatch):
        # This is the regression test for both bugs: importing
        # RETAIL_DB_PATH (which doesn't exist) used to blow up before
        # run_eval() could even be called, and calling it used to raise
        # sources.SourceError immediately because "eval_user" was never
        # connected. Getting a well-formed result dict back at all,
        # without either exception, is the point of this test.
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient("SELECT COUNT(*) FROM customers"))

        result = run_eval(username="eval_test_user")

        assert set(result.keys()) == {"validation_rate", "execution_rate", "match_rate"}

    def test_a_correct_generation_counts_as_a_full_pass(self, monkeypatch):
        # Every gold_sql in BENCHMARK_QUESTIONS is a SELECT against
        # RetailDB — stubbing the model to always return a trivially
        # correct, always-matching query proves the validation/execution/
        # row-count-comparison pipeline itself works end to end.
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient("SELECT * FROM customers"))
        monkeypatch.setattr(
            "evals.eval_sql.BENCHMARK_QUESTIONS",
            [{"id": 1, "question": "anything", "gold_sql": "SELECT * FROM customers"}],
        )

        result = run_eval(username="eval_test_user2")

        assert result["validation_rate"] == 1.0
        assert result["execution_rate"] == 1.0
        assert result["match_rate"] == 1.0

    def test_a_row_count_mismatch_is_not_counted_as_an_exact_match(self, monkeypatch):
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient("SELECT * FROM customers LIMIT 1"))
        monkeypatch.setattr(
            "evals.eval_sql.BENCHMARK_QUESTIONS",
            [{"id": 1, "question": "anything", "gold_sql": "SELECT * FROM customers"}],
        )

        result = run_eval(username="eval_test_user3")

        assert result["execution_rate"] == 1.0  # it ran fine...
        assert result["match_rate"] == 0.0      # ...but the row counts don't match

    def test_invalid_generated_sql_is_caught_not_crashed(self, monkeypatch):
        monkeypatch.setattr(llm, "_get_client", lambda: _FakeGroqClient("SELECT * FROM not_a_real_table"))
        monkeypatch.setattr(
            "evals.eval_sql.BENCHMARK_QUESTIONS",
            [{"id": 1, "question": "anything", "gold_sql": "SELECT * FROM customers"}],
        )

        result = run_eval(username="eval_test_user4")

        assert result["validation_rate"] == 0.0

    def test_benchmark_question_set_is_well_formed(self):
        assert len(BENCHMARK_QUESTIONS) >= 15
        seen_ids = set()
        for q in BENCHMARK_QUESTIONS:
            assert q["question"]
            assert q["gold_sql"].strip().upper().startswith("SELECT")
            assert q["id"] not in seen_ids
            seen_ids.add(q["id"])

    def test_every_gold_sql_actually_executes_against_the_real_demo_schema(self):
        demo_db.init_db(force=True)
        import sqlite3
        conn = sqlite3.connect(demo_db.DB_PATH)
        try:
            for q in BENCHMARK_QUESTIONS:
                conn.execute(q["gold_sql"])  # raises sqlite3.Error on a bad query
        finally:
            conn.close()
