import time

from dotenv import load_dotenv

load_dotenv()  # must run before any module reads os.environ, so load first

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, history, schema_meta, sources
from .llm import generate_sql, generate_table_descriptions, MAX_DESCRIPTION_TABLES
from .sql_guard import SQLValidationError, validate_sql

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth.init_auth_db()
    # History is always available regardless of which data source (if any)
    # is active. The data source itself is NOT auto-connected here — the
    # user picks one after signing in.
    history.init_history_db()
    schema_meta.init_schema_meta_db()
    yield


app = FastAPI(title="SQLscribe API", version="1.0.0", lifespan=lifespan)

import os
import re

ALLOWED_ORIGINS_RAW = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173,http://localhost:3000"
)
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hard cap on rows returned to the browser in one go. A generated query
# with no LIMIT (or an accidental cross join) could otherwise pull an
# entire table into memory and freeze the results grid. We ask the
# driver for one extra row so we can tell "exactly MAX_ROWS" apart from
# "there were more" without a second COUNT(*) round-trip.
MAX_ROWS = 500


def _dedupe_columns(columns: list[str]) -> list[str]:
    """Guard against duplicate column names in the result set (e.g. a
    generated query joins two tables that both have a `name` column
    without aliasing). dict(zip(columns, row)) would otherwise silently
    drop every duplicate but the last one, losing data with no error
    surfaced anywhere. Renames repeats to name, name_2, name_3, ..."""
    seen: dict[str, int] = {}
    result = []
    for col in columns:
        if col not in seen:
            seen[col] = 1
            result.append(col)
        else:
            seen[col] += 1
            result.append(f"{col}_{seen[col]}")
    return result


@app.get("/")
def root():
    return {
        "message": "SQLscribe API is running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/signup")
def signup(req: SignupRequest):
    try:
        return auth.signup(req.username, req.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/auth/login")
def login(req: LoginRequest):
    try:
        return auth.login(req.username, req.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/api/auth/logout")
def logout(current_user: str = Depends(auth.require_auth), authorization: str = Header(default=None)):
    # current_user via require_auth also validates the token is real before
    # we bother deleting it.
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    if token:
        auth.logout(token)
    return {"ok": True}


@app.get("/api/auth/me")
def me(current_user: str = Depends(auth.require_auth)):
    return {"username": current_user}


# ---------------------------------------------------------------------------
# Data source selection (signed-in users only)
# ---------------------------------------------------------------------------

class PostgresConnectRequest(BaseModel):
    host: str
    port: int | None = 5432
    database: str
    user: str
    password: str


class MySQLConnectRequest(BaseModel):
    host: str
    port: int | None = 3306
    database: str
    user: str
    password: str


class SqlitePathRequest(BaseModel):
    path: str


DIALECT_DISPLAY_NAMES = {"sqlite": "SQLite", "postgres": "PostgreSQL", "mysql": "MySQL"}


@app.get("/api/source")
def get_source(current_user: str = Depends(auth.require_auth)):
    return sources.get_source_info(current_user)


@app.post("/api/source/disconnect")
def disconnect_source(current_user: str = Depends(auth.require_auth)):
    sources.disconnect(current_user)
    return sources.get_source_info(current_user)


@app.post("/api/source/demo")
def connect_demo(current_user: str = Depends(auth.require_auth)):
    res = sources.connect_demo(current_user)
    schema_meta.truncate_for_source(current_user, res["name"], keep_custom=True)
    return res


@app.post("/api/source/sqlite")
async def connect_sqlite(file: UploadFile, current_user: str = Depends(auth.require_auth)):
    if not (file.filename or "").lower().endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=422, detail="Please upload a .db or .sqlite file.")
    file_bytes = await file.read()
    try:
        res = sources.connect_sqlite(current_user, file_bytes, file.filename)
        schema_meta.truncate_for_source(current_user, res["name"], keep_custom=True)
        return res
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/sqlite-path")
def connect_sqlite_path(req: SqlitePathRequest, current_user: str = Depends(auth.require_auth)):
    try:
        res = sources.connect_sqlite_path(current_user, req.path)
        schema_meta.truncate_for_source(current_user, res["name"], keep_custom=True)
        return res
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/postgres")
def connect_postgres(req: PostgresConnectRequest, current_user: str = Depends(auth.require_auth)):
    try:
        res = sources.connect_postgres(current_user, req.host, req.port, req.database, req.user, req.password)
        schema_meta.truncate_for_source(current_user, res["name"], keep_custom=True)
        return res
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/mysql")
def connect_mysql(req: MySQLConnectRequest, current_user: str = Depends(auth.require_auth)):
    try:
        res = sources.connect_mysql(current_user, req.host, req.port, req.database, req.user, req.password)
        schema_meta.truncate_for_source(current_user, res["name"], keep_custom=True)
        return res
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@app.get("/api/schema")
def schema(current_user: str = Depends(auth.require_auth)):
    if not sources.is_connected(current_user):
        raise HTTPException(status_code=400, detail="No data source connected yet.")
    info = sources.get_source_info(current_user)
    return {"database": info["name"], "tables": sources.get_schema_metadata(current_user)}


# ---------------------------------------------------------------------------
# Table descriptions ("meta table")
#
# A per-table, human-readable description store that supplements the raw
# schema with what each table actually means — used both to enrich the
# LLM's prompt (see llm._build_schema_context) and to show in the Schema
# tab UI. Generation is a single batched LLM call per source (not one per
# table), triggered explicitly rather than automatically on every
# connect, so reconnecting to a source you've already described doesn't
# burn an extra LLM call for no reason.
# ---------------------------------------------------------------------------

def _require_source(current_user: str) -> dict:
    if not sources.is_connected(current_user):
        raise HTTPException(status_code=400, detail="No data source connected yet.")
    return sources.get_source_info(current_user)


@app.get("/api/schema/descriptions")
def get_table_descriptions(current_user: str = Depends(auth.require_auth)):
    info = _require_source(current_user)
    return {
        "database": info["name"],
        "descriptions": schema_meta.get_descriptions(current_user, info["name"]),
    }


@app.post("/api/schema/descriptions/generate")
def generate_table_descriptions_endpoint(
    overwrite_custom: bool = Query(False),
    current_user: str = Depends(auth.require_auth),
):
    info = _require_source(current_user)
    database_name = info["name"]

    try:
        generated = generate_table_descriptions(current_user)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

    # Truncate-then-refill: clear out the previous generated descriptions.
    # keep_custom=not overwrite_custom preserves manual edits unless caller explicitly opts in.
    schema_meta.truncate_for_source(current_user, database_name, keep_custom=not overwrite_custom)
    schema_meta.save_generated(
        current_user,
        database_name,
        table_descriptions=generated.get("tables"),
        column_descriptions=generated.get("columns"),
    )

    return {
        "database": database_name,
        "descriptions": schema_meta.get_descriptions(current_user, database_name),
        "note": (
            f"Generated descriptions for the first {MAX_DESCRIPTION_TABLES} tables. "
            f"{len(generated['skipped_tables'])} more table(s) need a manual description: "
            f"{', '.join(generated['skipped_tables'])}."
        ) if generated.get("skipped_tables") else None,
    }


class TableDescriptionRequest(BaseModel):
    description: str


class ColumnDescriptionRequest(BaseModel):
    description: str


@app.put("/api/schema/descriptions/{table_name}")
def set_table_description(
    table_name: str, req: TableDescriptionRequest, current_user: str = Depends(auth.require_auth)
):
    info = _require_source(current_user)
    description = req.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description cannot be empty.")

    allowed_tables = {t["name"] for t in sources.get_schema_metadata(current_user)}
    if table_name not in allowed_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found in the active schema.")

    schema_meta.set_custom_description(current_user, info["name"], table_name, description)
    return {
        "database": info["name"],
        "descriptions": schema_meta.get_descriptions(current_user, info["name"]),
    }


@app.delete("/api/schema/descriptions/{table_name}")
def delete_table_description(table_name: str, current_user: str = Depends(auth.require_auth)):
    info = _require_source(current_user)
    schema_meta.clear_description(current_user, info["name"], table_name)
    return {
        "database": info["name"],
        "descriptions": schema_meta.get_descriptions(current_user, info["name"]),
    }


@app.put("/api/schema/descriptions/{table_name}/columns/{column_name}")
def set_column_description(
    table_name: str,
    column_name: str,
    req: ColumnDescriptionRequest,
    current_user: str = Depends(auth.require_auth),
):
    info = _require_source(current_user)
    description = req.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description cannot be empty.")

    schema_tables = {
        t["name"]: {c["name"] for c in t["columns"]}
        for t in sources.get_schema_metadata(current_user)
    }
    if table_name not in schema_tables:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found in active schema.")
    if column_name not in schema_tables[table_name]:
        raise HTTPException(
            status_code=404, detail=f"Column '{column_name}' not found in table '{table_name}'."
        )

    schema_meta.set_custom_column_description(current_user, info["name"], table_name, column_name, description)
    return {
        "database": info["name"],
        "descriptions": schema_meta.get_descriptions(current_user, info["name"]),
    }


@app.delete("/api/schema/descriptions/{table_name}/columns/{column_name}")
def delete_column_description(
    table_name: str, column_name: str, current_user: str = Depends(auth.require_auth)
):
    info = _require_source(current_user)
    schema_meta.clear_column_description(current_user, info["name"], table_name, column_name)
    return {
        "database": info["name"],
        "descriptions": schema_meta.get_descriptions(current_user, info["name"]),
    }



# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    elapsed_ms: int
    validated: bool
    dialect: str
    read_only: bool = True
    truncated: bool = False
    # True when this is a generated write query (INSERT/UPDATE/DELETE/DDL)
    # that has been validated but NOT executed yet. The frontend must show
    # the SQL to the user and call /api/query/confirm before anything is
    # committed to the database. columns/rows/row_count are empty in this
    # case since nothing has run.
    pending_confirmation: bool = False


def _execute_and_record(safe_sql: str, is_read_only: bool, question: str, dialect: str, start: float, username: str) -> QueryResponse:
    """Run an already-validated SQL statement, record it in history, and
    build the response. Shared by the direct (read-only) path in
    run_query and the confirm path in confirm_query — the actual
    execution/commit only ever happens here, in one place."""
    conn = sources.get_connection(username)
    state = sources._get_state(username)
    source_type = state.get("type", "sqlite")

    try:
        cursor = conn.cursor()
        
        # Enforce execution timeout (10s limit) per database dialect
        if source_type == "postgres":
            try:
                cursor.execute("SET LOCAL statement_timeout = 10000")
            except Exception:
                pass
        elif source_type == "mysql":
            try:
                cursor.execute("SET SESSION max_execution_time = 10000")
            except Exception:
                pass

        cursor.execute(safe_sql)

        if not is_read_only:
            conn.commit()

        if cursor.description:
            raw_columns = [d[0] for d in cursor.description]
            columns = _dedupe_columns(raw_columns)
            fetched = cursor.fetchmany(MAX_ROWS + 1)
            truncated = len(fetched) > MAX_ROWS
            if truncated:
                fetched = fetched[:MAX_ROWS]
            rows = [dict(zip(columns, row)) for row in fetched]
        else:
            columns = ["status", "affected_rows"]
            affected = cursor.rowcount if cursor.rowcount >= 0 else 0
            rows = [{"status": "Query executed successfully", "affected_rows": affected}]
            truncated = False
    except Exception as exc:
        if not is_read_only:
            try:
                conn.rollback()
            except Exception:
                pass
        err_msg = str(exc)
        # Sanitize exception output so sensitive parameters are never leaked in error response body
        for secret_key in ("password", "pwd", "secret", "token"):
            err_msg = re.sub(rf"{secret_key}=['\"]?\S+['\"]?", f"{secret_key}=***", err_msg, flags=re.IGNORECASE)
        # Belt-and-suspenders: also strip this user's actual stored DB
        # password verbatim, in case it appears in the driver's message
        # without a "password=" prefix the regex above would catch (some
        # drivers echo the whole DSN, or just the bare value, on auth
        # failure).
        err_msg = sources.redact_for_user(username, err_msg)
        raise HTTPException(status_code=422, detail=f"Query execution failed: {err_msg}")
    finally:
        conn.close()

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    dialect_display = DIALECT_DISPLAY_NAMES.get(dialect, "SQLite")
    source_name = sources.get_source_info(username).get("name", "")

    history.record(username, question, safe_sql, dialect_display, columns, rows, len(rows), elapsed_ms, database_name=source_name)

    return QueryResponse(
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        elapsed_ms=elapsed_ms,
        validated=True,
        dialect=dialect_display,
        read_only=is_read_only,
        truncated=truncated,
    )


def _generate_and_validate(question: str, dialect: str, allowed_tables: set[str], username: str) -> tuple[str, bool]:
    """Ask the LLM for SQL and run it through sql_guard, retrying once
    with the validator's error fed back in. Returns (safe_sql, is_read_only)
    or raises HTTPException."""
    safe_sql = None
    is_read_only = True
    last_error = None
    # Give the model up to two attempts: a bad first generation (truncation,
    # a stray formatting artifact, an unknown column) shouldn't dead-end the
    # user — the second attempt sees exactly what went wrong.
    for attempt in range(2):
        try:
            raw_sql = generate_sql(question, username, dialect=dialect, retry_hint=last_error)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")

        try:
            safe_sql, is_read_only = validate_sql(raw_sql, allowed_tables=allowed_tables, dialect=dialect)
            break
        except SQLValidationError as exc:
            last_error = exc.message
            continue

    if safe_sql is None:
        raise HTTPException(status_code=422, detail=last_error)

    return safe_sql, is_read_only


@app.post("/api/query", response_model=QueryResponse)
def run_query(req: QueryRequest, current_user: str = Depends(auth.require_auth)):
    auth.check_query_rate_limit(current_user)
    if not sources.is_connected(current_user):
        raise HTTPException(status_code=400, detail="No data source connected yet.")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    dialect = sources.get_dialect(current_user)
    schema_tables = sources.get_schema_metadata(current_user)
    allowed_tables = {t["name"] for t in schema_tables}
    start = time.perf_counter()

    safe_sql, is_read_only = _generate_and_validate(question, dialect, allowed_tables, current_user)

    # SELECT queries run immediately — nothing to confirm, there's nothing
    # to undo. INSERT/UPDATE/DELETE/DDL statements change real data, so we
    # stop here and hand the validated SQL back to the frontend for the
    # user to explicitly confirm before anything is committed.
    if not is_read_only:
        dialect_display = DIALECT_DISPLAY_NAMES.get(dialect, "SQLite")
        return QueryResponse(
            sql=safe_sql,
            columns=[],
            rows=[],
            row_count=0,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            validated=True,
            dialect=dialect_display,
            read_only=False,
            truncated=False,
            pending_confirmation=True,
        )

    return _execute_and_record(safe_sql, is_read_only, question, dialect, start, current_user)


class QueryConfirmRequest(BaseModel):
    question: str
    sql: str


@app.post("/api/query/confirm", response_model=QueryResponse)
def confirm_query(req: QueryConfirmRequest, current_user: str = Depends(auth.require_auth)):
    """Execute a write query the user has explicitly reviewed and
    confirmed. The SQL is re-validated from scratch here — never trust
    that a client-supplied string is still safe to run just because it
    was validated once already; the schema or connected database could
    have changed in between."""
    auth.check_query_rate_limit(current_user)
    if not sources.is_connected(current_user):
        raise HTTPException(status_code=400, detail="No data source connected yet.")

    question = req.question.strip()
    sql_text = req.sql.strip()
    if not sql_text:
        raise HTTPException(status_code=400, detail="No SQL to confirm.")

    dialect = sources.get_dialect(current_user)
    schema_tables = sources.get_schema_metadata(current_user)
    allowed_tables = {t["name"] for t in schema_tables}
    start = time.perf_counter()

    try:
        safe_sql, is_read_only = validate_sql(sql_text, allowed_tables=allowed_tables, dialect=dialect)
    except SQLValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    return _execute_and_record(safe_sql, is_read_only, question, dialect, start, current_user)


@app.get("/api/history")
def get_history(limit: int = 10, database_name: str | None = None, current_user: str = Depends(auth.require_auth)):
    if not database_name and sources.is_connected(current_user):
        database_name = sources.get_source_info(current_user).get("name")
    return {"history": history.recent(current_user, limit=limit, database_name=database_name)}


class FavoriteRequest(BaseModel):
    is_favorite: bool


@app.patch("/api/history/{entry_id}/favorite")
def set_history_favorite(
    entry_id: int, req: FavoriteRequest, current_user: str = Depends(auth.require_auth)
):
    updated = history.set_favorite(current_user, entry_id, req.is_favorite)
    if not updated:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return {"ok": True, "is_favorite": req.is_favorite}


@app.delete("/api/history/{entry_id}")
def delete_history_entry(entry_id: int, current_user: str = Depends(auth.require_auth)):
    deleted = history.delete_entry(current_user, entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return {"ok": True}



@app.delete("/api/history")
def clear_history(database_name: str | None = None, current_user: str = Depends(auth.require_auth)):
    if not database_name and sources.is_connected(current_user):
        database_name = sources.get_source_info(current_user).get("name")
    history.clear_all(current_user, database_name=database_name)
    return {"ok": True}