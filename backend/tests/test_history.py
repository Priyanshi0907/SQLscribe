"""
Tests for app/history.py — mainly the per-user isolation fix. Before this
fix, `current_user` was required to call any history endpoint but never
actually used to filter or scope anything, so any signed-in user could
read, favorite, or delete any other user's query history.
"""

from app import history


def _record_for(username: str, question: str) -> int:
    return history.record(
        username, question, "SELECT 1", "SQLite",
        columns=["1"], rows=[{"1": 1}], row_count=1, elapsed_ms=5,
        database_name="RetailDB",
    )


class TestPerUserIsolation:
    def test_user_only_sees_their_own_history(self):
        _record_for("alice", "alice's question")
        _record_for("bob", "bob's question")

        alice_questions = [h["question"] for h in history.recent("alice")]
        bob_questions = [h["question"] for h in history.recent("bob")]

        assert alice_questions == ["alice's question"]
        assert bob_questions == ["bob's question"]

    def test_user_cannot_delete_another_users_entry(self):
        alice_id = _record_for("alice", "alice's question")

        deleted = history.delete_entry("bob", alice_id)

        assert deleted is False
        assert len(history.recent("alice")) == 1

    def test_user_cannot_favorite_another_users_entry(self):
        alice_id = _record_for("alice", "alice's question")

        updated = history.set_favorite("bob", alice_id, True)

        assert updated is False
        assert history.recent("alice")[0]["is_favorite"] is False

    def test_user_can_delete_their_own_entry(self):
        alice_id = _record_for("alice", "alice's question")

        deleted = history.delete_entry("alice", alice_id)

        assert deleted is True
        assert history.recent("alice") == []

    def test_clear_all_only_clears_the_calling_users_history(self):
        _record_for("alice", "alice's question")
        _record_for("bob", "bob's question")

        history.clear_all("alice")

        assert history.recent("alice") == []
        assert len(history.recent("bob")) == 1


class TestDatabaseNameFiltering:
    def test_filters_by_database_name_within_one_users_history(self):
        history.record(
            "alice", "q1", "SELECT 1", "SQLite", ["1"], [{"1": 1}], 1, 5,
            database_name="RetailDB",
        )
        history.record(
            "alice", "q2", "SELECT 1", "SQLite", ["1"], [{"1": 1}], 1, 5,
            database_name="OtherDB",
        )

        retail_only = history.recent("alice", database_name="RetailDB")

        assert [h["question"] for h in retail_only] == ["q1"]
