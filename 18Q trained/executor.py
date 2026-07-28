"""
executor.py
-----------
Real execution layer — runs validated SQL against demo.db (created by
setup_db.py) using parameterized/direct sqlite3 execution, and returns
rows in a JSON-friendly format.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "demo.db"


def execute_sql(sql: str):
    """
    Returns (success: bool, result_or_error)

    On success: result is a list of dicts (rows) for SELECT, or a
    dict with rowcount for INSERT/UPDATE.
    On failure: result_or_error is the exception message.
    """
    if not DB_PATH.exists():
        return False, "demo.db not found — run setup_db.py first."

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql.rstrip(";"))

        if sql.strip().upper().startswith("SELECT"):
            rows = [dict(row) for row in cursor.fetchall()]
            return True, rows
        else:
            conn.commit()
            return True, {"rows_affected": cursor.rowcount}

    except sqlite3.Error as e:
        return False, str(e)
    finally:
        conn.close()
