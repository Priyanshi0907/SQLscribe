"""
Data-source management.

SQLscribe can point at several kinds of database, chosen on the landing
screen before the chat interface unlocks:
  - "demo"     the seeded RetailDB SQLite file shipped with the project
  - "sqlite"   a .db/.sqlite file the user uploaded, or a path to one
               already on the server
  - "postgres" a live PostgreSQL server the user supplied credentials for
  - "mysql"    a live MySQL/MariaDB server the user supplied credentials for

State is keyed per signed-in username, not a single process-wide global —
two users signed in at once (or the same user in two tabs) each get their
own active connection instead of fighting over one shared value. This is
still in-memory (resets on backend restart, and doesn't sync across
multiple backend processes behind a load balancer) — fine for a
single-process demo deployment; a real multi-instance deployment would
move this into a shared store like Redis keyed the same way.
"""

import os
import sqlite3
import time
import uuid
from pathlib import Path

import psycopg2
import pymysql

from . import database as demo_db
from .session_store import default_session_store as _session_store

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

# connect_sqlite_path() lets a signed-in user type a filesystem path and
# have the server open it — useful for pointing at a SQLite file already
# on the machine without re-uploading it through the browser, but without
# a boundary that's an arbitrary local-file-read primitive: any user
# could type a path to another user's uploaded database, a backup file,
# or anything else the server process can read. Restricting it to one
# designated directory keeps the convenience (drop a file in, connect by
# name) without the arbitrary-path risk.
LOCAL_SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "local_sources"

_DEFAULT_STATE = {
    "type": None,           # "demo" | "sqlite" | "postgres" | "mysql"
    "name": None,            # display name shown in the UI
    "sqlite_path": None,
    "pg_config": None,       # dict: host, port, dbname, user, password
    "mysql_config": None,    # dict: host, port, database, user, password
}

# Per-user connection state now actually goes through session_store.py's
# BaseSessionStore interface (previously that file existed but nothing
# called it — sources.py kept its own separate raw dict). `_sessions`
# stays a module-level name pointing at the store's own backing dict —
# not a copy — purely so existing call sites and tests that do
# `sources._sessions.clear()` / `sources._sessions[username]` keep
# working unchanged; all *new* reads/writes go through
# _session_store.get_session()/set_session() below, which is the actual
# seam a Redis-backed store would replace.
_sessions: dict[str, dict] = _session_store._sessions


def _get_state(username: str) -> dict:
    state = _session_store.get_session(username)
    if state is None:
        state = dict(_DEFAULT_STATE)
        _session_store.set_session(username, state)
    return state


class SourceError(Exception):
    pass


def _redact_secret(message: str, secret: str | None) -> str:
    """Replace a known secret value with a placeholder inside a string —
    used so a raw driver exception (which can embed the DSN, including
    the password, in its text) never reaches an HTTP response verbatim."""
    if not secret:
        return message
    return message.replace(secret, "[redacted]")


def redact_for_user(username: str, message: str) -> str:
    """Strip this user's currently-stored DB password(s) out of any
    string before it's returned to the browser. Call this on any error
    message that might have come from the database driver — a failed
    query against an already-connected Postgres/MySQL source is the
    main case, since psycopg2/pymysql exceptions occasionally include
    connection details in their text."""
    state = _session_store.get_session(username)
    if not state:
        return message
    redacted = message
    for config_key in ("pg_config", "mysql_config"):
        config = state.get(config_key)
        if config:
            redacted = _redact_secret(redacted, config.get("password"))
    return redacted


def is_connected(username: str) -> bool:
    return _get_state(username)["type"] is not None


def get_dialect(username: str) -> str:
    state = _get_state(username)
    if state["type"] == "postgres":
        return "postgres"
    if state["type"] == "mysql":
        return "mysql"
    return "sqlite"


def get_source_info(username: str) -> dict:
    return {
        "connected": is_connected(username),
        "type": _get_state(username)["type"],
        "name": _get_state(username)["name"],
        "dialect": get_dialect(username) if is_connected(username) else None,
    }


def disconnect(username: str) -> None:
    _session_store.set_session(username, dict(_DEFAULT_STATE))


def connect_demo(username: str) -> dict:
    demo_db.init_db()
    state = _get_state(username)
    state.update(
        type="demo", name="RetailDB", sqlite_path=demo_db.DB_PATH,
        pg_config=None, mysql_config=None,
    )
    return get_source_info(username)


def _validate_sqlite_file(path: Path) -> None:
    """Raises SourceError if the file at `path` isn't a real SQLite
    database with at least one table."""
    try:
        conn = sqlite3.connect(path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.close()
    except sqlite3.DatabaseError as exc:
        raise SourceError(f"That doesn't look like a valid SQLite file: {exc}")
    if not tables:
        raise SourceError("That SQLite file doesn't have any tables to query.")


def connect_sqlite(username: str, file_bytes: bytes, filename: str) -> dict:
    """Connect to an uploaded SQLite file (bytes from the browser)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or "upload.db"
    # Namespaced by a random suffix (not the username) so two different
    # uploads with the same filename never collide, from the same user
    # or different ones.
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest.write_bytes(file_bytes)

    try:
        _validate_sqlite_file(dest)
    except SourceError:
        dest.unlink(missing_ok=True)
        raise

    state = _get_state(username)
    state.update(
        type="sqlite", name=safe_name, sqlite_path=dest,
        pg_config=None, mysql_config=None,
    )
    return get_source_info(username)


def connect_sqlite_path(username: str, path: str) -> dict:
    """Connect to a SQLite file already present on the server, referenced
    by name rather than uploaded through the browser.

    Deliberately restricted to LOCAL_SOURCES_DIR rather than accepting
    any filesystem path: without that boundary, a signed-in user could
    type a path to any SQLite-formatted file the server process can
    read — another user's uploaded database, a backup, anything — and
    this endpoint would happily open it. `path` can be given as just a
    filename ("mydata.db") or a path relative to LOCAL_SOURCES_DIR; an
    absolute path or one using ".." to climb out of that directory is
    rejected outright, before the filesystem is even touched.
    """
    LOCAL_SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    requested = Path(path)
    if requested.is_absolute() or ".." in requested.parts:
        raise SourceError(
            "Path must be a filename inside the server's local-sources "
            "directory, not an absolute path or one that walks outside it."
        )

    file_path = (LOCAL_SOURCES_DIR / requested).resolve()
    allowed_root = LOCAL_SOURCES_DIR.resolve()
    if not file_path.is_relative_to(allowed_root):
        raise SourceError("That path is outside the allowed directory.")
    if not file_path.is_file():
        raise SourceError(
            f"No file found at '{path}' in the server's local-sources "
            f"directory ({allowed_root})."
        )

    _validate_sqlite_file(file_path)

    state = _get_state(username)
    state.update(
        type="sqlite", name=file_path.name, sqlite_path=file_path,
        pg_config=None, mysql_config=None,
    )
    return get_source_info(username)


def connect_postgres(username: str, host: str, port, database: str, user: str, password: str) -> dict:
    config = dict(
        host=host, port=int(port) if port else 5432,
        dbname=database, user=user, password=password,
    )
    try:
        conn = psycopg2.connect(connect_timeout=5, **config)
        conn.close()
    except Exception as exc:
        raise SourceError(_redact_secret(f"Couldn't connect to PostgreSQL: {exc}", password))

    state = _get_state(username)
    state.update(
        type="postgres", name=database, sqlite_path=None,
        pg_config=config, mysql_config=None,
    )
    return get_source_info(username)


def connect_mysql(username: str, host: str, port, database: str, user: str, password: str) -> dict:
    config = dict(
        host=host, port=int(port) if port else 3306,
        database=database, user=user, password=password,
    )
    try:
        conn = pymysql.connect(connect_timeout=5, **config)
        conn.close()
    except Exception as exc:
        raise SourceError(_redact_secret(f"Couldn't connect to MySQL: {exc}", password))

    state = _get_state(username)
    state.update(
        type="mysql", name=database, sqlite_path=None,
        pg_config=None, mysql_config=config,
    )
    return get_source_info(username)


# Max wall-clock seconds a single generated query is allowed to run
# before being cancelled server-side — a generated query is untrusted
# input from the model's perspective (could be an accidental cross join,
# a missing index, a pathological CTE), and letting it run unbounded
# ties up a connection indefinitely. Configurable since "reasonable" for
# a small demo table isn't the same as for a large real database.
QUERY_TIMEOUT_SECONDS = float(os.environ.get("SQLSCRIBE_QUERY_TIMEOUT_SECONDS", "25"))


def _apply_sqlite_timeout(conn: sqlite3.Connection, timeout_seconds: float) -> None:
    """SQLite has no native query-timeout setting — the standard
    workaround is a progress handler: SQLite calls it periodically
    during query execution, and returning a truthy value aborts the
    query with sqlite3.OperationalError. Checking wall-clock time here
    (rather than counting a fixed number of calls) keeps the timeout
    accurate regardless of how expensive each VM instruction is."""
    deadline = time.monotonic() + timeout_seconds

    def _handler():
        return time.monotonic() > deadline

    # n=1000 means "check roughly every 1000 SQLite VM instructions" —
    # frequent enough to cut off a runaway query promptly, infrequent
    # enough not to meaningfully slow down a normal one.
    conn.set_progress_handler(_handler, 1000)


def _apply_postgres_timeout(conn, timeout_seconds: float) -> None:
    cur = conn.cursor()
    cur.execute(f"SET statement_timeout = {int(timeout_seconds * 1000)}")


def _apply_mysql_timeout(conn, timeout_seconds: float) -> None:
    cur = conn.cursor()
    # MAX_EXECUTION_TIME is milliseconds and only applies to SELECTs on
    # MySQL (5.7.8+) — still worth setting even though this app's DML
    # paths are already narrower (single-statement, WHERE-scoped) than
    # what this mainly guards against.
    cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_seconds * 1000)}")


def get_connection(username: str):
    state = _get_state(username)
    if not is_connected(username):
        raise SourceError("No data source connected yet.")
    if state["type"] == "postgres":
        conn = psycopg2.connect(**state["pg_config"])
        try:
            _apply_postgres_timeout(conn, QUERY_TIMEOUT_SECONDS)
        except Exception:
            pass  # a timeout we couldn't set is better than failing the whole connection over it
        return conn
    if state["type"] == "mysql":
        conn = pymysql.connect(**state["mysql_config"])
        try:
            _apply_mysql_timeout(conn, QUERY_TIMEOUT_SECONDS)
        except Exception:
            pass
        return conn
    conn = sqlite3.connect(state["sqlite_path"])
    conn.row_factory = sqlite3.Row
    _apply_sqlite_timeout(conn, QUERY_TIMEOUT_SECONDS)
    return conn


def _get_postgres_foreign_keys(conn) -> dict[str, list[dict]]:
    """Real FK constraints declared in the database, not name-matching
    guesses — {table_name: [{"column", "references_table",
    "references_column"}, ...]}. This is what lets the LLM (and the
    frontend ER diagram) show actual relationships instead of inferring
    them from a `*_id` naming convention that a real-world schema may not
    even follow."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            tc.table_name AS table_name,
            kcu.column_name AS column_name,
            ccu.table_name AS references_table,
            ccu.column_name AS references_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
        """
    )
    by_table: dict[str, list[dict]] = {}
    for table_name, column_name, references_table, references_column in cur.fetchall():
        by_table.setdefault(table_name, []).append({
            "column": column_name,
            "references_table": references_table,
            "references_column": references_column,
        })
    return by_table


def _get_mysql_foreign_keys(conn, database: str) -> dict[str, list[dict]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name, column_name, referenced_table_name, referenced_column_name
        FROM information_schema.key_column_usage
        WHERE table_schema = %s AND referenced_table_name IS NOT NULL
        """,
        (database,),
    )
    by_table: dict[str, list[dict]] = {}
    for table_name, column_name, references_table, references_column in cur.fetchall():
        by_table.setdefault(table_name, []).append({
            "column": column_name,
            "references_table": references_table,
            "references_column": references_column,
        })
    return by_table


def _get_sqlite_foreign_keys(conn, table: str) -> list[dict]:
    """PRAGMA foreign_key_list returns one row per FK column, columns
    (id, seq, table, from, to, on_update, on_delete, match) — `table` is
    the referenced table, `from`/`to` are the local/referenced columns."""
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    return [
        {"column": r["from"], "references_table": r["table"], "references_column": r["to"]}
        for r in rows
    ]


def get_schema_metadata(username: str) -> list[dict]:
    """Introspect whatever database this user currently has active.
    Works for any SQLite file (demo or uploaded), PostgreSQL database, or
    MySQL database — nothing here is hardcoded to a specific set of
    table names.

    Each table dict now also carries a "foreign_keys" list — real FK
    constraints read from the database's own catalog/pragma, not the
    naming-convention guesses the frontend ER diagram previously relied
    on exclusively (see frontend/src/lib/schemaRelationships.js, which
    now prefers these when present and only falls back to guessing for
    tables that declare no FK constraints at all)."""
    state = _get_state(username)
    if not is_connected(username):
        raise SourceError("No data source connected yet.")

    if state["type"] == "postgres":
        conn = get_connection(username)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
                """
            )
            pk_cols = {(row[0], row[1]) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            by_table = {}
            for table_name, column_name, data_type in cur.fetchall():
                by_table.setdefault(table_name, []).append(
                    {
                        "name": column_name,
                        "type": data_type.upper(),
                        "pk": (table_name, column_name) in pk_cols,
                    }
                )
            fks_by_table = _get_postgres_foreign_keys(conn)
            result = []
            for name, columns in by_table.items():
                count_cur = conn.cursor()
                count_cur.execute(f'SELECT COUNT(*) FROM "{name}"')
                row_count = count_cur.fetchone()[0]
                result.append({
                    "name": name, "row_count": row_count, "columns": columns,
                    "foreign_keys": fks_by_table.get(name, []),
                })
            return result
        finally:
            conn.close()

    if state["type"] == "mysql":
        conn = get_connection(username)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND column_key = 'PRI'
                """,
                (state["mysql_config"]["database"],),
            )
            pk_cols = {(row[0], row[1]) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (state["mysql_config"]["database"],),
            )
            by_table = {}
            for table_name, column_name, data_type in cur.fetchall():
                by_table.setdefault(table_name, []).append(
                    {
                        "name": column_name,
                        "type": data_type.upper(),
                        "pk": (table_name, column_name) in pk_cols,
                    }
                )
            fks_by_table = _get_mysql_foreign_keys(conn, state["mysql_config"]["database"])
            result = []
            for name, columns in by_table.items():
                count_cur = conn.cursor()
                count_cur.execute(f"SELECT COUNT(*) FROM `{name}`")
                row_count = count_cur.fetchone()[0]
                result.append({
                    "name": name, "row_count": row_count, "columns": columns,
                    "foreign_keys": fks_by_table.get(name, []),
                })
            return result
        finally:
            conn.close()

    # sqlite (demo, uploaded, or connected by path)
    conn = get_connection(username)
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        result = []
        for row in tables:
            table = row["name"]
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            row_count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            result.append({
                "name": table,
                "row_count": row_count,
                "columns": [{"name": c["name"], "type": c["type"], "pk": bool(c["pk"] > 0)} for c in cols],
                "foreign_keys": _get_sqlite_foreign_keys(conn, table),
            })
        return result
    finally:
        conn.close()
