import time

from dotenv import load_dotenv

load_dotenv()  # must run before any module reads os.environ, so load first

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, history, sources
from .llm import generate_sql
from .sql_guard import SQLValidationError, validate_sql

app = FastAPI(title="SQLscribe API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
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


@app.on_event("startup")
def on_startup():
    auth.init_auth_db()
    # History is always available regardless of which data source (if any)
    # is active. The data source itself is NOT auto-connected here — the
    # user picks one after signing in.
    history.init_history_db()


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
    return sources.get_source_info()


@app.post("/api/source/disconnect")
def disconnect_source(current_user: str = Depends(auth.require_auth)):
    sources.disconnect()
    return sources.get_source_info()


@app.post("/api/source/demo")
def connect_demo(current_user: str = Depends(auth.require_auth)):
    return sources.connect_demo()


@app.post("/api/source/sqlite")
async def connect_sqlite(file: UploadFile, current_user: str = Depends(auth.require_auth)):
    if not (file.filename or "").lower().endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(status_code=422, detail="Please upload a .db or .sqlite file.")
    file_bytes = await file.read()
    try:
        return sources.connect_sqlite(file_bytes, file.filename)
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/sqlite-path")
def connect_sqlite_path(req: SqlitePathRequest, current_user: str = Depends(auth.require_auth)):
    try:
        return sources.connect_sqlite_path(req.path)
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/postgres")
def connect_postgres(req: PostgresConnectRequest, current_user: str = Depends(auth.require_auth)):
    try:
        return sources.connect_postgres(req.host, req.port, req.database, req.user, req.password)
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/source/mysql")
def connect_mysql(req: MySQLConnectRequest, current_user: str = Depends(auth.require_auth)):
    try:
        return sources.connect_mysql(req.host, req.port, req.database, req.user, req.password)
    except sources.SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@app.get("/api/schema")
def schema(current_user: str = Depends(auth.require_auth)):
    if not sources.is_connected():
        raise HTTPException(status_code=400, detail="No data source connected yet.")
    info = sources.get_source_info()
    return {"database": info["name"], "tables": sources.get_schema_metadata()}


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


@app.post("/api/query", response_model=QueryResponse)
def run_query(req: QueryRequest, current_user: str = Depends(auth.require_auth)):
    if not sources.is_connected():
        raise HTTPException(status_code=400, detail="No data source connected yet.")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    dialect = sources.get_dialect()
    schema_tables = sources.get_schema_metadata()
    allowed_tables = {t["name"] for t in schema_tables}
    start = time.perf_counter()

    safe_sql = None
    is_read_only = True
    last_error = None
    # Give the model up to two attempts: a bad first generation (truncation,
    # a stray formatting artifact, an unknown column) shouldn't dead-end the
    # user — the second attempt sees exactly what went wrong.
    for attempt in range(2):
        try:
            raw_sql = generate_sql(question, dialect=dialect, retry_hint=last_error)
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

    conn = sources.get_connection()
    try:
        cursor = conn.cursor()
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
        raise HTTPException(status_code=422, detail=f"Query execution failed: {exc}")
    finally:
        conn.close()

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    dialect_display = DIALECT_DISPLAY_NAMES.get(dialect, "SQLite")

    history.record(question, safe_sql, dialect_display, columns, rows, len(rows), elapsed_ms)

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


@app.get("/api/history")
def get_history(limit: int = 10, current_user: str = Depends(auth.require_auth)):
    return {"history": history.recent(limit)}


class FavoriteRequest(BaseModel):
    is_favorite: bool


@app.patch("/api/history/{entry_id}/favorite")
def set_history_favorite(
    entry_id: int, req: FavoriteRequest, current_user: str = Depends(auth.require_auth)
):
    updated = history.set_favorite(entry_id, req.is_favorite)
    if not updated:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return {"ok": True, "is_favorite": req.is_favorite}


@app.delete("/api/history/{entry_id}")
def delete_history_entry(entry_id: int, current_user: str = Depends(auth.require_auth)):
    deleted = history.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History entry not found.")
    return {"ok": True}


@app.delete("/api/history")
def clear_history(current_user: str = Depends(auth.require_auth)):
    history.clear_all()
    return {"ok": True}