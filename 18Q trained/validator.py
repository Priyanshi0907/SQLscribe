"""
validator.py
------------
Real validation layer — matches report suggested stack:
"SQL parser (e.g. sqlglot) to check syntax, table/column whitelist, and
WHERE-clause enforcement" (Section 6).
"""

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"customers", "orders", "order_items", "products"}

ALLOWED_COLUMNS = {
    "customers": {"customer_id", "name", "email", "city"},
    "orders": {"order_id", "customer_id", "order_date", "status"},
    "order_items": {"order_item_id", "order_id", "product_id", "quantity"},
    "products": {"product_id", "product_name", "category", "price"},
}

BLOCKED_STATEMENT_TYPES = (exp.Drop, exp.TruncateTable, exp.Delete, exp.Alter)


def validate_sql(sql: str):
    """
    Returns (is_valid: bool, error_message: str | None)

    Checks, in order:
    1. Parses cleanly (syntax check)
    2. Not a blocked operation (DROP/TRUNCATE/DELETE/ALTER)
    3. Only references whitelisted tables
    4. UPDATE statements must include a WHERE clause
    5. Only references whitelisted columns per table
    """
    sql = sql.strip().rstrip(";")

    if sql.startswith("ERROR:"):
        return False, sql

    # 1. Syntax check
    try:
        parsed = sqlglot.parse_one(sql, dialect="sqlite")
    except Exception as e:
        return False, f"SQL syntax error: {e}"

    if parsed is None:
        return False, "Could not parse SQL — empty or malformed statement."

    # 2. Blocked operation types
    if isinstance(parsed, BLOCKED_STATEMENT_TYPES):
        return False, f"Operation '{type(parsed).__name__.upper()}' is not permitted."

    # 3. Table whitelist
    referenced_tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
    unknown_tables = referenced_tables - ALLOWED_TABLES
    if unknown_tables:
        return False, f"Unknown table(s) referenced: {', '.join(unknown_tables)}"

    # 4. WHERE clause enforcement on UPDATE
    if isinstance(parsed, exp.Update):
        where_clause = parsed.find(exp.Where)
        if where_clause is None:
            return False, "UPDATE statement is missing a WHERE clause — unscoped updates are not allowed."

    # 5. Column whitelist
    defined_aliases = {a.alias.lower() for a in parsed.find_all(exp.Alias) if a.alias}

    for col in parsed.find_all(exp.Column):
        col_name = col.name.lower()
        table_hint = col.table.lower() if col.table else None
        if col_name == "*" or col_name in defined_aliases:
            continue
        if table_hint and table_hint in ALLOWED_COLUMNS:
            if col_name not in ALLOWED_COLUMNS[table_hint]:
                return False, f"Unknown column '{col_name}' on table '{table_hint}'."
        elif not table_hint:
            if not any(col_name in cols for cols in ALLOWED_COLUMNS.values()):
                return False, f"Unknown column '{col_name}' — does not match any known table."

    return True, None
