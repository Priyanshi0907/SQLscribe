"""
Table-description metadata store ("the meta table").

SQLscribe's LLM prompt (see llm.py's _build_schema_context) only had raw
table/column names and types to work with — no notion of what a table is
*for*. That's fine for a clean demo schema like RetailDB, but falls apart
on real-world schemas with abbreviated or ambiguous names (`tbl_ord_hdr`,
`flag_1`, `amt_x`...). This module stores a human-readable description per
table, generated once (in a single batched LLM call — see
llm.generate_table_descriptions) and reusable across every future query
against that same data source, instead of paying an LLM round trip on
every single question.

Kept in its own local SQLite file, the same pattern history.py and
auth.py use — independent of whichever data source is currently active,
so switching from the demo DB to an uploaded file never risks writing a
`_sqlscribe_meta` table into someone's real database.

Descriptions are scoped per (username, database_name) — two different
users, or the same user connected to two differently-named sources, each
get their own independent set. "database_name" is the display name
sources.py assigns a connection (e.g. "RetailDB", an uploaded filename,
or a Postgres/MySQL database name) — not a filesystem path, so it stays
meaningful even after the underlying file/connection is gone.

Regenerating (POST /api/schema/descriptions/generate) truncates the
existing rows for that (username, database_name) pair before inserting
fresh ones, so re-running it against a schema that changed shape (extra
tables, renamed columns) doesn't leave stale descriptions mixed in with
new ones. Manual edits made through the UI are flagged is_custom=True and
are always the versions returned/used — the intent is "the LLM gives you
a first draft, you can correct it," not "the LLM silently overwrites your
correction the next time someone clicks Regenerate." Regeneration only
replaces custom edits if the caller explicitly opts in (see
generate_and_save's overwrite_custom flag).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_META_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "schema_meta.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS table_descriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    database_name TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    is_custom     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(username, database_name, table_name)
);

CREATE TABLE IF NOT EXISTS column_descriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    database_name TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    column_name   TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    is_custom     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(username, database_name, table_name, column_name)
);
"""


def init_schema_meta_db() -> None:
    SCHEMA_META_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SCHEMA_META_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SCHEMA_META_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_descriptions(username: str, database_name: str) -> dict[str, dict]:
    """Returns {table_name: {"description": str, "is_custom": bool, "columns": {col_name: {"description": str, "is_custom": bool}}}}
    for every table/column this user has a saved description for, under this
    database name."""
    conn = _get_conn()
    t_rows = conn.execute(
        "SELECT table_name, description, is_custom FROM table_descriptions "
        "WHERE username = ? AND database_name = ?",
        (username, database_name),
    ).fetchall()

    c_rows = conn.execute(
        "SELECT table_name, column_name, description, is_custom FROM column_descriptions "
        "WHERE username = ? AND database_name = ?",
        (username, database_name),
    ).fetchall()
    conn.close()

    result: dict[str, dict] = {}
    for r in t_rows:
        result[r["table_name"]] = {
            "description": r["description"],
            "is_custom": bool(r["is_custom"]),
            "columns": {},
        }

    for r in c_rows:
        t_name = r["table_name"]
        if t_name not in result:
            result[t_name] = {
                "description": "",
                "is_custom": False,
                "columns": {},
            }
        result[t_name]["columns"][r["column_name"]] = {
            "description": r["description"],
            "is_custom": bool(r["is_custom"]),
        }

    return result


def truncate_for_source(username: str, database_name: str, *, keep_custom: bool = True) -> None:
    """Clear out descriptions for this (user, database) pair before a
    regeneration pass. keep_custom=True (the default) preserves any
    manually-edited rows so a Regenerate click can't silently clobber a
    correction the user already made."""
    conn = _get_conn()
    if keep_custom:
        conn.execute(
            "DELETE FROM table_descriptions WHERE username = ? AND database_name = ? AND is_custom = 0",
            (username, database_name),
        )
        conn.execute(
            "DELETE FROM column_descriptions WHERE username = ? AND database_name = ? AND is_custom = 0",
            (username, database_name),
        )
    else:
        conn.execute(
            "DELETE FROM table_descriptions WHERE username = ? AND database_name = ?",
            (username, database_name),
        )
        conn.execute(
            "DELETE FROM column_descriptions WHERE username = ? AND database_name = ?",
            (username, database_name),
        )
    conn.commit()
    conn.close()


def save_generated(
    username: str,
    database_name: str,
    table_descriptions: dict[str, str] | None = None,
    column_descriptions: dict[str, dict[str, str]] | None = None,
) -> None:
    """Upsert a batch of LLM-generated table and column descriptions. Never overwrites a
    row already flagged is_custom."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()

    if table_descriptions:
        for table_name, description in table_descriptions.items():
            existing = conn.execute(
                "SELECT is_custom FROM table_descriptions "
                "WHERE username = ? AND database_name = ? AND table_name = ?",
                (username, database_name, table_name),
            ).fetchone()
            if existing and existing["is_custom"]:
                continue
            conn.execute(
                "INSERT INTO table_descriptions "
                "(username, database_name, table_name, description, is_custom, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?, ?) "
                "ON CONFLICT(username, database_name, table_name) DO UPDATE SET "
                "description = excluded.description, is_custom = 0, updated_at = excluded.updated_at",
                (username, database_name, table_name, description, now, now),
            )

    if column_descriptions:
        for table_name, col_map in column_descriptions.items():
            if not isinstance(col_map, dict):
                continue
            for column_name, description in col_map.items():
                existing = conn.execute(
                    "SELECT is_custom FROM column_descriptions "
                    "WHERE username = ? AND database_name = ? AND table_name = ? AND column_name = ?",
                    (username, database_name, table_name, column_name),
                ).fetchone()
                if existing and existing["is_custom"]:
                    continue
                conn.execute(
                    "INSERT INTO column_descriptions "
                    "(username, database_name, table_name, column_name, description, is_custom, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, ?) "
                    "ON CONFLICT(username, database_name, table_name, column_name) DO UPDATE SET "
                    "description = excluded.description, is_custom = 0, updated_at = excluded.updated_at",
                    (username, database_name, table_name, column_name, description, now, now),
                )

    conn.commit()
    conn.close()


def set_custom_description(username: str, database_name: str, table_name: str, description: str) -> None:
    """A manual edit from the UI form for a table description."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO table_descriptions "
        "(username, database_name, table_name, description, is_custom, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, ?, ?) "
        "ON CONFLICT(username, database_name, table_name) DO UPDATE SET "
        "description = excluded.description, is_custom = 1, updated_at = excluded.updated_at",
        (username, database_name, table_name, description, now, now),
    )
    conn.commit()
    conn.close()


def set_custom_column_description(
    username: str, database_name: str, table_name: str, column_name: str, description: str
) -> None:
    """A manual edit from the UI form for a column description."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO column_descriptions "
        "(username, database_name, table_name, column_name, description, is_custom, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?) "
        "ON CONFLICT(username, database_name, table_name, column_name) DO UPDATE SET "
        "description = excluded.description, is_custom = 1, updated_at = excluded.updated_at",
        (username, database_name, table_name, column_name, description, now, now),
    )
    conn.commit()
    conn.close()


def clear_description(username: str, database_name: str, table_name: str) -> None:
    conn = _get_conn()
    conn.execute(
        "DELETE FROM table_descriptions WHERE username = ? AND database_name = ? AND table_name = ?",
        (username, database_name, table_name),
    )
    conn.commit()
    conn.close()


def clear_column_description(username: str, database_name: str, table_name: str, column_name: str) -> None:
    conn = _get_conn()
    conn.execute(
        "DELETE FROM column_descriptions WHERE username = ? AND database_name = ? AND table_name = ? AND column_name = ?",
        (username, database_name, table_name, column_name),
    )
    conn.commit()
    conn.close()

