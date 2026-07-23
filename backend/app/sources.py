"""
Data-source management.

SQLscribe can point at several kinds of database, chosen on the landing
screen before the chat interface unlocks:
  - "demo"     the seeded RetailDB SQLite file shipped with the project
  - "sqlite"   a .db/.sqlite file the user uploaded, or a path to one
               already on the server
  - "postgres" a live PostgreSQL server the user supplied credentials for
  - "mysql"    a live MySQL/MariaDB server the user supplied credentials for

Exactly one source is active at a time, held in memory on this module.
This is a deliberate MVP simplification for a single-session demo — if
this is ever served to more than one user concurrently, this needs to
become per-session state (keyed by a session/user id) instead of one
process-wide global, since right now two browser tabs would fight over
the same active connection.
"""

import sqlite3
import uuid
from pathlib import Path

import psycopg2
import pymysql

from . import database as demo_db

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"

_state = {
    "type": None,        # "demo" | "sqlite" | "postgres" | "mysql"
    "name": None,          # display name shown in the UI
    "sqlite_path": None,
    "pg_config": None,     # dict: host, port, dbname, user, password
    "mysql_config": None,  # dict: host, port, database, user, password
}


class SourceError(Exception):
    pass


def is_connected() -> bool:
    return _state["type"] is not None


def get_dialect() -> str:
    if _state["type"] == "postgres":
        return "postgres"
    if _state["type"] == "mysql":
        return "mysql"
    return "sqlite"


def get_source_info() -> dict:
    return {
        "connected": is_connected(),
        "type": _state["type"],
        "name": _state["name"],
        "dialect": get_dialect() if is_connected() else None,
    }


def disconnect() -> None:
    _state.update(type=None, name=None, sqlite_path=None, pg_config=None, mysql_config=None)


def connect_demo() -> dict:
    demo_db.init_db()
    _state.update(
        type="demo", name="RetailDB", sqlite_path=demo_db.DB_PATH,
        pg_config=None, mysql_config=None,
    )
    return get_source_info()


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


def connect_sqlite(file_bytes: bytes, filename: str) -> dict:
    """Connect to an uploaded SQLite file (bytes from the browser)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-") or "upload.db"
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest.write_bytes(file_bytes)

    try:
        _validate_sqlite_file(dest)
    except SourceError:
        dest.unlink(missing_ok=True)
        raise

    _state.update(
        type="sqlite", name=safe_name, sqlite_path=dest,
        pg_config=None, mysql_config=None,
    )
    return get_source_info()


def connect_sqlite_path(path: str) -> dict:
    """Connect to a SQLite file already present on the server filesystem,
    referenced by path rather than uploaded."""
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise SourceError(f"No file found at {path}")

    _validate_sqlite_file(file_path)

    _state.update(
        type="sqlite", name=file_path.name, sqlite_path=file_path,
        pg_config=None, mysql_config=None,
    )
    return get_source_info()


def connect_postgres(host: str, port, database: str, user: str, password: str) -> dict:
    config = dict(
        host=host, port=int(port) if port else 5432,
        dbname=database, user=user, password=password,
    )
    try:
        conn = psycopg2.connect(connect_timeout=5, **config)
        conn.close()
    except Exception as exc:
        raise SourceError(f"Couldn't connect to PostgreSQL: {exc}")

    _state.update(
        type="postgres", name=database, sqlite_path=None,
        pg_config=config, mysql_config=None,
    )
    return get_source_info()


def connect_mysql(host: str, port, database: str, user: str, password: str) -> dict:
    config = dict(
        host=host, port=int(port) if port else 3306,
        database=database, user=user, password=password,
    )
    try:
        conn = pymysql.connect(connect_timeout=5, **config)
        conn.close()
    except Exception as exc:
        raise SourceError(f"Couldn't connect to MySQL: {exc}")

    _state.update(
        type="mysql", name=database, sqlite_path=None,
        pg_config=None, mysql_config=config,
    )
    return get_source_info()


def get_connection():
    if not is_connected():
        raise SourceError("No data source connected yet.")
    if _state["type"] == "postgres":
        return psycopg2.connect(**_state["pg_config"])
    if _state["type"] == "mysql":
        return pymysql.connect(**_state["mysql_config"])
    conn = sqlite3.connect(_state["sqlite_path"])
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_metadata() -> list[dict]:
    """Introspect whatever database is currently active. Works for any
    SQLite file (demo or uploaded), PostgreSQL database, or MySQL
    database — nothing here is hardcoded to a specific set of table names."""
    if not is_connected():
        raise SourceError("No data source connected yet.")

    if _state["type"] == "postgres":
        conn = get_connection()
        try:
            cur = conn.cursor()
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
                    {"name": column_name, "type": data_type.upper()}
                )
            result = []
            for name, columns in by_table.items():
                count_cur = conn.cursor()
                count_cur.execute(f'SELECT COUNT(*) FROM "{name}"')
                row_count = count_cur.fetchone()[0]
                result.append({"name": name, "row_count": row_count, "columns": columns})
            return result
        finally:
            conn.close()

    if _state["type"] == "mysql":
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (_state["mysql_config"]["database"],),
            )
            by_table = {}
            for table_name, column_name, data_type in cur.fetchall():
                by_table.setdefault(table_name, []).append(
                    {"name": column_name, "type": data_type.upper()}
                )
            result = []
            for name, columns in by_table.items():
                count_cur = conn.cursor()
                count_cur.execute(f"SELECT COUNT(*) FROM `{name}`")
                row_count = count_cur.fetchone()[0]
                result.append({"name": name, "row_count": row_count, "columns": columns})
            return result
        finally:
            conn.close()

    # sqlite (demo, uploaded, or connected by path)
    conn = get_connection()
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
                "columns": [{"name": c["name"], "type": c["type"]} for c in cols],
            })
        return result
    finally:
        conn.close()