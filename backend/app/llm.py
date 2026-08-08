"""
Natural language -> SQL generation via the Groq API (Llama 3.3 70B).

This is the only file that talks to the LLM. It builds a prompt from the
live schema of whichever data source is currently active (so the model
never hallucinates table/column names or writes syntax the connected
database can't run), sends it to the Groq API, and extracts a single
SQL statement from the response.
"""

import json
import os
import re

from groq import Groq

from . import schema_meta, sources

# "llama-3.3-70b-versatile" is Groq's flagship fast & accurate model.
MODEL = os.environ.get("SQLSCRIBE_MODEL", "llama-3.3-70b-versatile")

_client: Groq | None = None

DIALECT_NAMES = {"sqlite": "SQLite", "postgres": "PostgreSQL", "mysql": "MySQL"}


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to backend/.env "
                "(see .env.example)."
            )
        _client = Groq(api_key=api_key)
    return _client


def _build_schema_context(username: str) -> str:
    """Builds the schema block injected into the system prompt.

    Beyond bare `table(col type, ...)` lines, this folds in table and column
    descriptions as well as foreign key relationships.
    """
    tables = sources.get_schema_metadata(username)
    if not tables:
        return "(No existing tables in database)"

    database_name = sources.get_source_info(username).get("name") or ""
    descriptions = schema_meta.get_descriptions(username, database_name)

    lines = []
    relationship_lines = []
    for t in tables:
        cols = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
        line = f"- {t['name']}({cols})"
        t_meta = descriptions.get(t["name"], {})
        desc = t_meta.get("description")
        if desc:
            line += f"  -- {desc}"
        lines.append(line)

        col_meta_map = t_meta.get("columns", {})
        for c in t["columns"]:
            c_desc = col_meta_map.get(c["name"], {}).get("description")
            if c_desc:
                lines.append(f"  * {c['name']}: {c_desc}")

        for fk in t.get("foreign_keys", []):
            relationship_lines.append(
                f"- {t['name']}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}"
            )

    schema_block = "\n".join(lines)
    if relationship_lines:
        schema_block += "\n\nForeign key relationships:\n" + "\n".join(relationship_lines)
    return schema_block


DESCRIPTION_SYSTEM_PROMPT = """You are a professional database documentation assistant embedded in SQLscribe.
Given a database schema (tables, columns, data types, and foreign key relationships), write concise, accurate, plain-English descriptions for:
1. Every single table in the schema (explaining what entity or business process it stores).
2. EVERY column in every table (explaining what data it contains, formatting details, or real-world meaning).

Rules:
- You MUST provide a description for EVERY table and EVERY column listed in the schema.
- Keep descriptions clear, professional, and natural (5-15 words per item).
- Output ONLY a single valid JSON object containing "tables" and "columns" keys. Do NOT add markdown formatting commentary.

Example JSON output structure:
{
  "tables": {
    "customers": "Customer information and profile records",
    "products": "Product catalog and inventory items"
  },
  "columns": {
    "customers": {
      "customer_id": "Unique customer identifier",
      "name": "Customer's full name",
      "email": "Customer's email address",
      "phone": "Customer's phone number, including country code",
      "city": "Customer's city of residence",
      "created_at": "Date the customer account was created"
    },
    "products": {
      "product_id": "Unique product identifier",
      "product_name": "Product name, e.g. Wireless Headphones",
      "category": "Product category, e.g. Electronics",
      "price": "Product price in decimal format",
      "stock_quantity": "Number of products in stock"
    }
  }
}
"""


def _extract_json_object(raw_text: str) -> dict:
    """Strip markdown fences/stray text the model might add despite
    instructions, then parse the first {...} object found."""
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)
    return json.loads(text)


MAX_DESCRIPTION_TABLES = 30


def generate_table_descriptions(username: str) -> dict[str, dict]:
    """Ask the LLM to describe every table and column in this user's active schema
    in a single batched call. Returns {"tables": {table_name: desc},
    "columns": {table_name: {column_name: desc}}, "skipped_tables": [names]}.

    Capped at MAX_DESCRIPTION_TABLES tables: a schema with dozens of
    tables would otherwise turn this into one very large, slow, and
    possibly-truncated prompt. Tables past the cap are left out of this
    pass rather than silently dropped — "skipped_tables" tells the
    caller exactly which ones still need a manual description (see
    main.py's generate endpoint, which turns this into a user-facing
    note)."""
    tables = sources.get_schema_metadata(username)
    if not tables:
        return {"tables": {}, "columns": {}, "skipped_tables": []}
    client = _get_client()

    tables_to_describe = tables[:MAX_DESCRIPTION_TABLES]
    skipped_tables = [t["name"] for t in tables[MAX_DESCRIPTION_TABLES:]]

    lines = []
    relationship_lines = []
    for t in tables_to_describe:
        cols = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
        lines.append(f"- {t['name']}({cols})")
        for fk in t.get("foreign_keys", []):
            relationship_lines.append(
                f"- {t['name']}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}"
            )
    schema_block = "\n".join(lines)
    if relationship_lines:
        schema_block += "\n\nForeign key relationships:\n" + "\n".join(relationship_lines)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": DESCRIPTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Schema:\n{schema_block}"},
        ],
        temperature=0.0,
        max_tokens=2000,
    )
    raw_text = response.choices[0].message.content or ""

    try:
        parsed = _extract_json_object(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeError(f"Model did not return valid JSON descriptions: {exc}")

    valid_tables = {t["name"]: {c["name"] for c in t["columns"]} for t in tables_to_describe}

    table_descs: dict[str, str] = {}
    col_descs: dict[str, dict[str, str]] = {}

    if "tables" in parsed and isinstance(parsed["tables"], dict):
        raw_tables = parsed["tables"]
        raw_cols = parsed.get("columns", {}) if isinstance(parsed.get("columns"), dict) else {}
    else:
        # Fallback for flat dictionary {table_name: desc}
        raw_tables = parsed
        raw_cols = {}

    for name, desc in raw_tables.items():
        if name in valid_tables and str(desc).strip():
            table_descs[name] = str(desc).strip()

    for t_name, c_dict in raw_cols.items():
        if t_name in valid_tables and isinstance(c_dict, dict):
            for c_name, c_desc in c_dict.items():
                if c_name in valid_tables[t_name] and str(c_desc).strip():
                    if t_name not in col_descs:
                        col_descs[t_name] = {}
                    col_descs[t_name][c_name] = str(c_desc).strip()

    col_descs = _reconcile_key_column_descriptions(tables_to_describe, col_descs)

    return {
        "tables": table_descs,
        "columns": col_descs,
        "skipped_tables": skipped_tables,
    }


def _reconcile_key_column_descriptions(tables: list[dict], col_descs: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """A foreign-key column shouldn't get its own independently-worded
    description from the model. Real FK data (from sources.py — PRAGMA
    foreign_key_list / information_schema, not a naming guess) already
    tells the UI which column a FK references and shows a "References
    table.column" badge right next to it — so if the model writes
    orders.customer_id and customers.customer_id differently, it reads
    like two different concepts describing the same real-world thing.

    This ALWAYS overwrites every FK column's description with whatever
    the model wrote for the column it actually references, whenever a
    description for that referenced column exists — not just when the
    FK column's own description happens to look empty or generic. A
    plausible-sounding but independently-worded FK description (e.g.
    "Identifies which customer placed this order") is exactly the case
    this needs to catch, not just the obviously-generic ones, so there's
    no "looks specific enough, leave it" carve-out here."""
    fk_by_table = {t["name"]: t.get("foreign_keys", []) for t in tables}
    has_any_real_fks = any(fk_by_table.values())

    if has_any_real_fks:
        for t in tables:
            for fk in fk_by_table.get(t["name"], []):
                referenced_desc = col_descs.get(fk["references_table"], {}).get(fk["references_column"])
                if referenced_desc:
                    col_descs.setdefault(t["name"], {})[fk["column"]] = referenced_desc
        return col_descs

    # No real FK constraints anywhere in this schema — fall back to
    # matching by the "first column = primary key" naming convention,
    # the same fallback frontend/src/lib/schemaRelationships.js uses for
    # drawing the ER diagram when a source declares no real FKs.
    pk_name_by_table = {}
    pk_description_by_colname = {}
    for t in tables:
        if not t["columns"]:
            continue
        pk_name = t["columns"][0]["name"]
        pk_name_by_table[t["name"]] = pk_name
        pk_desc = col_descs.get(t["name"], {}).get(pk_name)
        if pk_desc:
            pk_description_by_colname.setdefault(pk_name, pk_desc)

    for t in tables:
        own_pk_name = pk_name_by_table.get(t["name"])
        table_cols = col_descs.get(t["name"], {})
        for column_name in list(table_cols.keys()):
            if column_name == own_pk_name:
                continue
            reused = pk_description_by_colname.get(column_name)
            if reused:
                table_cols[column_name] = reused
    return col_descs



SYSTEM_PROMPT = """You are an expert SQL generation engine embedded in SQLscribe.
Your task is to convert any natural language query or instruction into a single, syntactically perfect, high-performance {dialect_name} SQL statement based on the database schema provided below.

Active Database Schema:
{schema}

Instructions & Execution Rules:
1. Support ALL SQL statement types requested by the user:
   - Queries & Insights: SELECT, CTEs (WITH clause), aggregations, window functions, GROUP BY, HAVING, subqueries.
   - Data Manipulation (DML): INSERT, UPDATE, DELETE.
   - Data Definition (DDL): CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE INDEX.
2. Dialect Specificity:
   - Generate SQL strictly adhering to {dialect_name} syntax conventions.
   - For SQLite: use standard string literals (single quotes), INTEGER PRIMARY KEY conventions, and SQLite date/time functions (`datetime('now')`, `strftime`, `date('now')`).
   - For PostgreSQL / MySQL: use appropriate dialect functions and quote identifiers accurately.
3. Schema Accuracy:
   - For SELECT/UPDATE/DELETE queries, reference existing tables and columns from the active schema.
   - Use clear, explicit JOIN conditions (`JOIN table ON ...`) rather than implicit comma joins.
   - Use concise table aliases (e.g. `c` for customers, `o` for orders).
   - When INSERTing data into tables, provide values matching column types. Omit primary key column if it is auto-incremented unless explicitly specified.
   - Every UPDATE and DELETE statement MUST include a WHERE clause that scopes it to specific rows (e.g. by primary key, or by a concrete condition drawn from the question). Never generate an UPDATE or DELETE with no WHERE clause, and never generate a WHERE clause that is trivially always true (e.g. `WHERE 1=1`) as a way around this — if the user's question doesn't give you enough to identify specific rows, filter as precisely as the question allows rather than omitting the clause.
4. Output Formatting:
   - Output ONLY the raw executable SQL statement.
   - Do NOT include markdown code fences (```sql), explanation, comments, or extra text.
   - Never end the statement with a semicolon (;).
"""


def _sanitize_control_chars(text: str) -> str:
    """Strip ANSI escape sequences and other non-printable control
    characters that occasionally leak into LLM text output and silently
    corrupt otherwise-valid SQL."""
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def _extract_sql(raw_text: str) -> str:
    """Strip markdown code fences and stray control characters if the
    model added them despite instructions."""
    text = _sanitize_control_chars(raw_text.strip())
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    return text.strip().strip(";").strip()


def generate_sql(question: str, username: str, dialect: str = "sqlite", retry_hint: str | None = None) -> str:
    """Send the question + schema to Groq and return the raw SQL text
    (not yet validated — the caller must run it through sql_guard).

    username: whose active data source to pull schema from — sources.py
    keeps connections per signed-in user, so this has to match the
    connection main.py is about to validate/execute against, or the
    model would be shown one user's schema while querying another's.

    retry_hint: when the caller's first attempt failed validation, it can
    pass the validator's error message back in here so the model gets one
    chance to see what went wrong and correct it."""
    client = _get_client()
    schema_context = _build_schema_context(username)
    dialect_name = DIALECT_NAMES.get(dialect, "SQLite")

    prompt = question
    if retry_hint:
        prompt = (
            f"User instruction: {question}\n\n"
            f"Your previous attempt generated SQL that failed with error: {retry_hint}\n"
            f"Analyze the error carefully and write a corrected, valid {dialect_name} SQL statement."
        )

    sys_instruction = SYSTEM_PROMPT.format(schema=schema_context, dialect_name=dialect_name)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_instruction},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1000,
    )

    raw_text = response.choices[0].message.content or ""
    return _extract_sql(raw_text)