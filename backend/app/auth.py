"""
Simple username/password authentication with bearer-token sessions.

This is intentionally lightweight for a demo/college project: SQLite-backed
users + a sessions table holding random tokens, checked via an
Authorization: Bearer <token> header. Passwords are hashed with bcrypt —
never stored or compared in plaintext.

What this deliberately does NOT do: password reset, email verification,
rate-limiting on login attempts, or token expiry. Fine for a portfolio
demo; swap in a real auth provider (Auth0, Clerk, etc.) before this goes
anywhere near production traffic.

Note: sign-in gates the app, but the data source picked in sources.py is
still a single process-wide value (see the limitation already called out
there) — every signed-in user shares the same active database connection.
Making data sources per-user would mean keying sources._state by username
instead of being a single global.
"""

import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import Header, HTTPException

AUTH_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "auth.db"

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
    created_at    TEXT NOT NULL
);
"""

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


class AuthError(Exception):
    pass


def init_auth_db() -> None:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.executescript(SCHEMA_SQL)
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
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row or not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
            raise AuthError("Incorrect username or password.")
        return _create_session(conn, username)
    finally:
        conn.close()


def _create_session(conn: sqlite3.Connection, username: str) -> dict:
    token = secrets.token_hex(32)
    conn.execute(
        "INSERT INTO sessions (token, username, created_at) VALUES (?, ?, ?)",
        (token, username, datetime.now(timezone.utc).isoformat()),
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
        "SELECT username FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    return row["username"] if row else None


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