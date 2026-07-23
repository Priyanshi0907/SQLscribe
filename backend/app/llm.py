"""
Natural language -> SQL generation via the Groq API (Llama 3.3 70B).

This is the only file that talks to the LLM. It builds a prompt from the
live schema of whichever data source is currently active (so the model
never hallucinates table/column names or writes syntax the connected
database can't run), sends it to the Groq API, and extracts a single
SQL statement from the response.
"""

import os
import re

from groq import Groq

from . import sources

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


def _build_schema_context() -> str:
    tables = sources.get_schema_metadata()
    if not tables:
        return "(No existing tables in database)"
    lines = []
    for t in tables:
        cols = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
        lines.append(f"- {t['name']}({cols})")
    return "\n".join(lines)


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


def generate_sql(question: str, dialect: str = "sqlite", retry_hint: str | None = None) -> str:
    """Send the question + schema to Groq and return the raw SQL text
    (not yet validated — the caller must run it through sql_guard).

    retry_hint: when the caller's first attempt failed validation, it can
    pass the validator's error message back in here so the model gets one
    chance to see what went wrong and correct it."""
    client = _get_client()
    schema_context = _build_schema_context()
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