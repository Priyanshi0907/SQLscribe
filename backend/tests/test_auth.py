"""
Tests for app/auth.py — signup/login flow and the login rate limiter.
"""

import pytest

from app import auth


class TestSignup:
    def test_signup_creates_a_session(self):
        result = auth.signup("kunal", "correcthorse123")
        assert result["username"] == "kunal"
        assert len(result["token"]) > 20

    def test_signup_rejects_short_password(self):
        with pytest.raises(auth.AuthError, match="8 characters"):
            auth.signup("kunal", "short")

    def test_signup_rejects_invalid_username(self):
        with pytest.raises(auth.AuthError, match="3-32 characters"):
            auth.signup("k", "correcthorse123")

    def test_signup_rejects_duplicate_username(self):
        auth.signup("kunal", "correcthorse123")
        with pytest.raises(auth.AuthError, match="already taken"):
            auth.signup("kunal", "anotherpassword")

    def test_password_is_hashed_not_stored_plaintext(self):
        auth.signup("kunal", "correcthorse123")
        conn = auth._get_conn()
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("kunal",)
        ).fetchone()
        conn.close()
        assert row["password_hash"] != "correcthorse123"
        assert row["password_hash"].startswith("$2b$")  # bcrypt prefix


class TestLogin:
    def test_login_with_correct_password_succeeds(self):
        auth.signup("kunal", "correcthorse123")
        result = auth.login("kunal", "correcthorse123")
        assert result["username"] == "kunal"

    def test_login_with_wrong_password_fails(self):
        auth.signup("kunal", "correcthorse123")
        with pytest.raises(auth.AuthError, match="Incorrect"):
            auth.login("kunal", "wrongpassword")

    def test_login_with_unknown_username_fails(self):
        with pytest.raises(auth.AuthError, match="Incorrect"):
            auth.login("nobody", "whatever123")

    def test_error_message_does_not_reveal_whether_username_exists(self):
        # Both a wrong password and a nonexistent username should produce
        # the exact same message — otherwise an attacker could enumerate
        # valid usernames by the error text alone.
        auth.signup("kunal", "correcthorse123")
        try:
            auth.login("kunal", "wrongpassword")
        except auth.AuthError as e:
            msg_wrong_password = str(e)
        try:
            auth.login("nobody", "whatever123")
        except auth.AuthError as e:
            msg_unknown_user = str(e)
        assert msg_wrong_password == msg_unknown_user


class TestSessionTokens:
    def test_valid_token_resolves_to_username(self):
        result = auth.signup("kunal", "correcthorse123")
        assert auth.get_username_for_token(result["token"]) == "kunal"

    def test_bogus_token_resolves_to_none(self):
        assert auth.get_username_for_token("not-a-real-token") is None

    def test_logout_invalidates_the_token(self):
        result = auth.signup("kunal", "correcthorse123")
        auth.logout(result["token"])
        assert auth.get_username_for_token(result["token"]) is None


class TestLoginRateLimiting:
    def test_lockout_after_repeated_failures(self):
        auth.signup("kunal", "correcthorse123")
        for _ in range(auth._LOGIN_ATTEMPT_LIMIT):
            with pytest.raises(auth.AuthError):
                auth.login("kunal", "wrongpassword")

        # Even the CORRECT password should now be blocked — this is what
        # actually proves it's a lockout, not just five more wrong guesses.
        with pytest.raises(auth.AuthError, match="Too many failed"):
            auth.login("kunal", "correcthorse123")

    def test_successful_login_resets_the_counter(self):
        auth.signup("kunal", "correcthorse123")
        with pytest.raises(auth.AuthError):
            auth.login("kunal", "wrongpassword")  # one failure, well under the limit
        auth.login("kunal", "correcthorse123")  # succeeds, resets the count

        # Counter was reset, so a fresh run of failures shouldn't already
        # be at the limit.
        for _ in range(auth._LOGIN_ATTEMPT_LIMIT - 1):
            with pytest.raises(auth.AuthError, match="Incorrect"):
                auth.login("kunal", "wrongpassword")

    def test_rate_limit_is_scoped_per_username(self):
        auth.signup("kunal", "correcthorse123")
        auth.signup("priya", "anothersecurepass")
        for _ in range(auth._LOGIN_ATTEMPT_LIMIT):
            with pytest.raises(auth.AuthError):
                auth.login("kunal", "wrongpassword")

        # kunal is locked out, but priya's own attempts are unaffected.
        result = auth.login("priya", "anothersecurepass")
        assert result["username"] == "priya"


class TestSessionExpiry:
    def test_fresh_token_is_valid(self):
        result = auth.signup("kunal", "correcthorse123")
        assert auth.get_username_for_token(result["token"]) == "kunal"

    def test_expired_token_is_rejected(self):
        from datetime import datetime, timedelta, timezone

        result = auth.signup("kunal", "correcthorse123")
        conn = auth._get_conn()
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE token = ?",
            (past, result["token"]),
        )
        conn.commit()
        conn.close()

        assert auth.get_username_for_token(result["token"]) is None

    def test_require_auth_rejects_expired_token_with_401(self):
        from datetime import datetime, timedelta, timezone

        result = auth.signup("kunal", "correcthorse123")
        conn = auth._get_conn()
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE token = ?",
            (past, result["token"]),
        )
        conn.commit()
        conn.close()

        with pytest.raises(Exception) as exc_info:
            auth.require_auth(f"Bearer {result['token']}")
        assert getattr(exc_info.value, "status_code", None) == 401

    def test_pre_migration_session_with_no_expiry_is_treated_as_expired(self):
        # Regression guard: a session row from before the expires_at
        # column existed (empty string) must not be grandfathered into
        # "valid forever" — it should be treated as already expired.
        result = auth.signup("kunal", "correcthorse123")
        conn = auth._get_conn()
        conn.execute(
            "UPDATE sessions SET expires_at = '' WHERE token = ?",
            (result["token"],),
        )
        conn.commit()
        conn.close()

        assert auth.get_username_for_token(result["token"]) is None
