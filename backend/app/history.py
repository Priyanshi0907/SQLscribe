"""
Query history storage.

Kept in its own local SQLite file, completely independent of whichever
data source is currently active. This matters: if history lived inside
the active database, switching from the demo DB to an uploaded file (or
a Postgres server) would either lose your history or pollute someone
else's real database with a query_history table they never asked for.

Full results (columns + rows) are stored alongside each entry, not just
the question and SQL — this is what lets the UI show a past query's
results instantly when you click it, without re-running it against the
database and creating a second, duplicate history entry.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HISTORY_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "history.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS query_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question      TEXT NOT NULL,
    sql_text      TEXT NOT NULL,
    dialect       TEXT NOT NULL DEFAULT 'SQLite',
    columns_json  TEXT NOT NULL DEFAULT '[]',
    rows_json     TEXT NOT NULL DEFAULT '[]',
    row_count     INTEGER NOT NULL,
    elapsed_ms    INTEGER NOT NULL,
    is_favorite   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    database_name TEXT NOT NULL DEFAULT ''
);
"""

# Columns added after the initial release. Added defensively via ALTER
# TABLE (ignoring "column already exists" errors) so a history.db file
# created by an earlier version of the app doesn't break on upgrade.
_MIGRATION_COLUMNS = [
    ("dialect", "TEXT NOT NULL DEFAULT 'SQLite'"),
    ("columns_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("rows_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("is_favorite", "INTEGER NOT NULL DEFAULT 0"),
    ("database_name", "TEXT NOT NULL DEFAULT ''"),
]


def init_history_db() -> None:
    HISTORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HISTORY_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    for name, coltype in _MIGRATION_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE query_history ADD COLUMN {name} {coltype}")
        except sqlite3.OperationalError:
            pass  # column already exists — fine
    # Set default database_name for legacy history records if empty
    conn.execute("UPDATE query_history SET database_name = 'RetailDB' WHERE database_name IS NULL OR database_name = ''")
    conn.commit()
    conn.close()


def record(
    question: str, sql_text: str, dialect: str,
    columns: list[str], rows: list[dict],
    row_count: int, elapsed_ms: int,
    database_name: str = "",
) -> int:
    conn = sqlite3.connect(HISTORY_DB_PATH)
    cur = conn.execute(
        "INSERT INTO query_history "
        "(question, sql_text, dialect, columns_json, rows_json, row_count, elapsed_ms, created_at, database_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            question, sql_text, dialect,
            json.dumps(columns), json.dumps(rows, default=str),
            row_count, elapsed_ms, datetime.now(timezone.utc).isoformat(),
            database_name,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def recent(limit: int = 10, database_name: str | None = None) -> list[dict]:
    conn = sqlite3.connect(HISTORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    if database_name:
        rows = conn.execute(
            "SELECT id, question, sql_text, dialect, columns_json, rows_json, "
            "row_count, elapsed_ms, is_favorite, created_at, database_name "
            "FROM query_history WHERE LOWER(database_name) = LOWER(?) ORDER BY id DESC LIMIT ?",
            (database_name, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, question, sql_text, dialect, columns_json, rows_json, "
            "row_count, elapsed_ms, is_favorite, created_at, database_name "
            "FROM query_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["columns"] = json.loads(d.pop("columns_json"))
        d["rows"] = json.loads(d.pop("rows_json"))
        d["is_favorite"] = bool(d["is_favorite"])
        result.append(d)
    return result


def set_favorite(entry_id: int, is_favorite: bool) -> bool:
    """Flip the pinned/favorite flag on one entry. Returns False if no
    entry with that id exists (caller turns that into a 404)."""
    conn = sqlite3.connect(HISTORY_DB_PATH)
    cur = conn.execute(
        "UPDATE query_history SET is_favorite = ? WHERE id = ?",
        (1 if is_favorite else 0, entry_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_entry(entry_id: int) -> bool:
    conn = sqlite3.connect(HISTORY_DB_PATH)
    cur = conn.execute("DELETE FROM query_history WHERE id = ?", (entry_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def clear_all(database_name: str | None = None) -> None:
    conn = sqlite3.connect(HISTORY_DB_PATH)
    if database_name:
        conn.execute("DELETE FROM query_history WHERE LOWER(database_name) = LOWER(?)", (database_name,))
    else:
        conn.execute("DELETE FROM query_history")
    conn.commit()
    conn.close()