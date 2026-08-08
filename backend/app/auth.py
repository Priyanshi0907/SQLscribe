"""
Simple username/password authentication with bearer-token sessions.

This is intentionally lightweight for a demo/college project: SQLite-backed
users + a sessions table holding random tokens, checked via an
Authorization: Bearer <token> header. Passwords are hashed with bcrypt —
never stored or compared in plaintext. Login attempts are rate-limited
per username (see _check_rate_limit below), and sessions expire after
SESSION_TTL_SECONDS rather than staying valid forever (see
_create_session / get_username_for_token below).

What this deliberately does NOT do: password reset or email
verification. Fine for a portfolio demo; swap in a real auth provider
(Auth0, Clerk, etc.) before this goes anywhere near production traffic.

One thing worth being upfront about: the frontend stores this bearer
token in localStorage (see frontend/src/lib/api.js), which is readable
by any JS that runs on the page — the standard tradeoff for a plain
bearer-token setup, versus an httpOnly cookie that JS can't touch at
all. Moving to httpOnly cookies was considered and deliberately not done
here: this frontend and backend run on different ports in dev
(127.0.0.1:5173 / 127.0.0.1:8000), which makes cookies cross-origin and
would require SameSite=None; Secure — i.e. HTTPS — to work at all,
breaking the plain `npm run dev` / `uvicorn --reload` local setup this
project is built around, and opening a CSRF surface that would need its
own mitigation. Token expiry is the mitigation actually shipped here: a
stolen token now has a bounded lifetime instead of being valid forever.

Note: sign-in gates the app, and the data source picked in sources.py is
now keyed per signed-in username too (see sources.py) — each user gets
their own active database connection rather than sharing one global.
"""

import re
import secrets
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import Header, HTTPException

AUTH_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "auth.db"

# How long a session token stays valid after login/signup. Chosen to be
# generous enough not to log a demo user out mid-session, while still
# meaning a leaked token isn't valid forever.
SESSION_TTL_SECONDS = 24 * 60 * 60

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token         TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL DEFAULT ''
);
"""

# expires_at was added after the initial release — defensively migrated
# via ALTER TABLE (like history.py does) so an existing auth.db doesn't
# break on upgrade. Sessions created before this migration have no
# expires_at and are treated as already-expired the first time they're
# looked up (see get_username_for_token) rather than guessed at.
_MIGRATION_COLUMNS = [("expires_at", "TEXT NOT NULL DEFAULT ''")]

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class AuthError(Exception):
    pass


# In-memory login rate limiting, keyed by username. This is intentionally
# process-local (resets on restart, doesn't sync across multiple backend
# instances) — consistent with the rest of this app's single-process
# design (see sources.py). It's enough to stop naive brute-forcing of one
# account without needing a separate store like Redis for a demo project.
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(username: str) -> None:
    now = time.monotonic()
    window_start = now - _LOGIN_ATTEMPT_WINDOW_SECONDS
    attempts = [t for t in _failed_attempts[username] if t > window_start]
    _failed_attempts[username] = attempts
    if len(attempts) >= _LOGIN_ATTEMPT_LIMIT:
        raise AuthError(
            f"Too many failed login attempts for this account. "
            f"Try again in a few minutes."
        )


def _record_failed_attempt(username: str) -> None:
    _failed_attempts[username].append(time.monotonic())


def _clear_failed_attempts(username: str) -> None:
    _failed_attempts.pop(username, None)


def init_auth_db() -> None:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    for name, coltype in _MIGRATION_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {coltype}")
        except sqlite3.OperationalError:
            pass  # column already exists — fine
    conn.commit()
    conn.close()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def signup(username: str, password: str) -> dict:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise AuthError(
            "Username must be 3-32 characters: letters, numbers, underscore, dot, or dash."
        )
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")

    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            raise AuthError("That username is already taken.")

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return _create_session(conn, username)
    finally:
        conn.close()


def login(username: str, password: str) -> dict:
    username = username.strip()
    _check_rate_limit(username)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            _record_failed_attempt(username)
            raise AuthError("Incorrect username or password.")
        _clear_failed_attempts(username)
        return _create_session(conn, username)
    finally:
        conn.close()


def _create_session(conn: sqlite3.Connection, username: str) -> dict:
    token = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    conn.execute(
        "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, username, now.isoformat(), expires_at.isoformat()),
    )
    conn.commit()
    return {"token": token, "username": username}


def logout(token: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def get_username_for_token(token: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT username, expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()

    if not row:
        conn.close()
        return None

    # Sessions from before the expires_at migration have an empty string
    # here, which parses as "already expired" rather than being treated
    # as valid-forever — a pre-migration token doesn't get grandfathered
    # into never expiring.
    try:
        expires_at = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        expires_at = datetime.min.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) >= expires_at:
        # Opportunistic cleanup — no separate background job needed for
        # a demo-scale sessions table.
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None

    conn.close()
    return row["username"]


_query_timestamps = defaultdict(list)
QUERY_RATE_LIMIT = 30  # max 30 queries per minute per user
QUERY_WINDOW_SECONDS = 60.0


def check_query_rate_limit(username: str) -> None:
    """Enforces a per-user query rate limit on /api/query endpoints."""
    now = time.time()
    cutoff = now - QUERY_WINDOW_SECONDS
    window = [t for t in _query_timestamps[username] if t > cutoff]
    if len(window) >= QUERY_RATE_LIMIT:
        oldest = min(window)
        retry_after = max(1, int(QUERY_WINDOW_SECONDS - (now - oldest)) + 1)
        raise HTTPException(
            status_code=429,
            detail=f"Query rate limit exceeded ({QUERY_RATE_LIMIT} queries/min). Please wait a moment.",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)
    _query_timestamps[username] = window


def require_auth(authorization: str = Header(default=None)) -> str:
    """FastAPI dependency — validates the Bearer token and returns the
    signed-in username, or raises 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in.")
    token = authorization.removeprefix("Bearer ").strip()
    username = get_username_for_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired — please sign in again.")
    return username