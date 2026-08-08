"""
SQL safety and syntax validation using sqlglot.

Every query returned by the LLM passes through here before execution.
It checks syntax validity, handles multi-statement safeguards, validates table
references against the connected database schema, and formats the query for
display in the frontend code panel.
"""

import re

import sqlglot
from sqlglot import exp

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """sqlglot's own ParseError messages embed ANSI underline codes around
    the offending token. Strip them before returning to user."""
    return _ANSI_RE.sub("", text)


class SQLValidationError(Exception):
    def __init__(self, message: str):
        self.message = _strip_ansi(message)
        super().__init__(self.message)


def _is_trivially_true(condition: exp.Expression) -> bool:
    """Catches the laziest ways to satisfy 'has a WHERE clause' without
    actually scoping anything — WHERE TRUE, WHERE 1=1, WHERE 'a'='a'."""
    if isinstance(condition, exp.Boolean) and condition.this is True:
        return True
    if isinstance(condition, exp.EQ):
        left, right = condition.left, condition.right
        if isinstance(left, exp.Literal) and isinstance(right, exp.Literal):
            return str(left.this) == str(right.this)
    return False


def _require_where_clause(parsed: exp.Expression) -> None:
    """UPDATE and DELETE must scope themselves to specific rows. This
    check is join-aware: a query filtered entirely through a JOIN ON
    condition (no WHERE at all) is just as capable of touching every row
    as one with no filter whatsoever, so the WHERE clause itself — not
    just 'the query looks complicated' — is what we require. Table
    references inside JOINs are still validated separately against the
    live schema by the caller, whether or not this check fires."""
    where = parsed.args.get("where")
    if where is None:
        kind = "DELETE" if isinstance(parsed, exp.Delete) else "UPDATE"
        raise SQLValidationError(
            f"{kind} statements must include a WHERE clause that identifies "
            f"specific rows. A statement with no WHERE clause would affect "
            f"every row in the table, so it's blocked before it ever reaches "
            f"the confirmation step."
        )
    if _is_trivially_true(where.this):
        kind = "DELETE" if isinstance(parsed, exp.Delete) else "UPDATE"
        raise SQLValidationError(
            f"{kind} statement's WHERE clause doesn't actually filter "
            f"anything (it's always true), which has the same effect as no "
            f"WHERE clause at all. Ask for a query that filters on specific "
            f"column values instead."
        )


def validate_sql(sql_text: str, allowed_tables: set[str], dialect: str = "sqlite") -> tuple[str, bool]:
    """
    Validate and normalize a generated SQL string against the live schema.

    Returns a tuple of (formatted_sql: str, is_read_only: bool).
    Raises SQLValidationError on syntax or structure failures.
    """
    if not sql_text or not sql_text.strip():
        raise SQLValidationError("Generated SQL was empty.")

    cleaned = _strip_ansi(sql_text.strip()).strip(";").strip()

    # Block obvious multi-statement injection before parsing.
    if ";" in cleaned:
        raise SQLValidationError("Multiple statements are not allowed in a single query.")

    # Block raw SQL comments that can disrupt execution or parsing.
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLValidationError(
            "SQL comments are not allowed in generated queries."
        )

    try:
        parsed = sqlglot.parse_one(cleaned, read=dialect)
    except Exception as exc:
        raise SQLValidationError(f"Could not parse generated SQL: {exc}")

    # Determine read-only status
    is_read_only = isinstance(parsed, exp.Select)

    # UPDATE/DELETE must be scoped to specific rows — checked before table
    # validation so the WHERE-clause error takes priority over an unknown-table
    # error when a query has both problems.
    if isinstance(parsed, (exp.Update, exp.Delete)):
        _require_where_clause(parsed)

    # Table validation
    if allowed_tables:
        allowed_lower = {t.lower() for t in allowed_tables}

        # If it's a CREATE TABLE statement, treat the target table as valid
        if isinstance(parsed, exp.Create):
            target = parsed.this
            if isinstance(target, exp.Schema):
                target = target.this
            if target and hasattr(target, "name") and target.name:
                allowed_lower.add(target.name.lower())

        # Collect CTE names declared in WITH clauses
        cte_names = set()
        for cte in parsed.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        # find_all(exp.Table) walks the entire parse tree, which already
        # covers every table pulled in through a JOIN — an UPDATE/DELETE
        # that joins against a table outside the connected schema is
        # rejected here exactly the same way a bare SELECT would be.
        referenced_tables = {t.name.lower() for t in parsed.find_all(exp.Table) if t.name}
        unknown = referenced_tables - allowed_lower - cte_names
        if unknown:
            raise SQLValidationError(
                f"Query references unknown table(s): {', '.join(sorted(unknown))}"
            )

    try:
        formatted = parsed.sql(dialect=dialect, pretty=True)
    except Exception:
        formatted = cleaned

    return formatted, is_read_only