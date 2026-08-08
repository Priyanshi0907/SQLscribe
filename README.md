# SQLscribe — Text-to-SQL Assistant

Ask a database questions in plain English and get back real, validated SQL
plus live results. Built with a FastAPI backend, a React + Tailwind
frontend, and the Groq API (Llama 3.3 70B) for natural language → SQL
generation.

Sign in, then choose your data source — a seeded demo database, your own
uploaded SQLite file, or a live PostgreSQL / MySQL server.

Theme: **Paper Terminal** — a bright, minimal interface with a dark,
terminal-style panel reserved just for the generated SQL.

```
Background  #FAF7F1     Cards    #FFFDF9
SQL Box     #2B2B2B     SQL text #7A5230
Primary     #5A6E5F     Accent   #B88746
Border      #E8E0D5
```

---

## What's included

- **Backend** (`/backend`) — FastAPI service that:
  - Gates the app behind username/password auth with bcrypt-hashed
    passwords and bearer-token sessions (see `app/auth.py`)
  - Lets you connect one of four data sources: a seeded demo SQLite
    database ("RetailDB"), an uploaded `.db`/`.sqlite` file, a live
    PostgreSQL server, or a live MySQL server (see `app/sources.py`)
  - Introspects whichever database is active — including its real
    foreign key constraints, read from the database's own catalog
    (`PRAGMA foreign_key_list` for SQLite, `information_schema` for
    Postgres/MySQL) rather than guessed from column-naming conventions —
    and sends that live schema to the Groq API to generate SQL —
    dialect-aware (SQLite / PostgreSQL / MySQL), never hardcoded to one
    schema
  - Generates a short, plain-English description for every table in a
    single batched LLM call, stores it in a small local "meta table"
    (`app/schema_meta.py`), and folds both the descriptions and the real
    FK relationships into the prompt context on every subsequent query
    (`app/llm.py`'s `_build_schema_context`) — see "Table descriptions"
    below for the full flow
  - Supports the full range of statement types the model can generate:
    SELECT, INSERT, UPDATE, DELETE, and DDL (CREATE/ALTER/DROP) — see
    "Safety model" below for how writes are gated
  - Validates every generated query before running it (single statement,
    no injected comments, only references tables that actually exist —
    see `app/sql_guard.py`)
  - Executes the query and returns results, logging each one to a
    separate local history store (`app/history.py`) that's independent
    of whichever data source is active, and scoped per signed-in user —
    your history is yours, not shared with anyone else using the app
- **Frontend** (`/frontend`) — React app matching the Paper Terminal
  design: sign-in screen, a data-source picker, a one-time table
  description review screen right after connecting, then the query
  interface — question box, terminal-style generated-SQL panel with
  syntax highlighting, a confirmation dialog for any write query,
  results table with CSV export, a live ER diagram (now drawn from real
  FK constraints when the database has them) in the Schema tab, an
  editable table-description panel, and query history.

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Groq API key: https://console.groq.com/keys
- (Optional) A PostgreSQL or MySQL server, only if you want to connect a
  live database instead of the demo or an uploaded SQLite file

## 1. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then open .env and paste in your GROQ_API_KEY

uvicorn app.main:app --reload --port 8000
```

Confirm it's running:
```bash
curl http://127.0.0.1:8000/api/health
```
Should return `{"status":"ok"}`. Nothing is auto-loaded at startup — you
sign in, then pick a data source from the UI.

## 2. Frontend setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The app talks to the backend at
`http://127.0.0.1:8000` by default — change `VITE_API_BASE` in a
`frontend/.env` file if you host the backend elsewhere.

## 3. Sign in

First load shows a sign-up/sign-in screen (`app/auth.py`,
`AuthScreen.jsx`). Passwords are bcrypt-hashed, login attempts are
rate-limited per username (5 failed attempts locks that username out for
15 minutes), and sessions expire 24 hours after login rather than
staying valid forever. Query history is scoped per user — signing in as
a different account shows a different history, and one user can't view,
favorite, or delete another user's entries.

One tradeoff worth being upfront about: the frontend keeps the session
token in `localStorage` (`frontend/src/lib/api.js`), which any JS
running on the page can read — the standard risk with plain bearer
tokens, versus an httpOnly cookie JS can't touch at all. Moving to
cookies was considered and deliberately not done: this project's
frontend and backend run on different ports in dev, which would make
the cookie cross-origin and require `SameSite=None; Secure` (i.e. HTTPS)
just to work, breaking plain `npm run dev` / `uvicorn --reload` local
development, and would add a CSRF surface needing its own mitigation.
Token expiry is the mitigation actually shipped instead — a leaked
token now has a bounded lifetime instead of being valid indefinitely.

Still intentionally lightweight for a demo/college project beyond that —
no password reset or email verification, and the rate limit + session
store are in-memory/single-SQLite-file (resets if the backend restarts,
doesn't sync across multiple backend processes). Swap in a real auth
provider before this goes anywhere near production traffic.

## 4. Pick a data source

After signing in you'll see:

- **Load Demo Database** — instant, seeds a small retail dataset
  (customers, products, orders, order_items) with zero setup.
- **Upload SQLite Database** — pick any `.db`/`.sqlite` file with real
  tables in it. The app introspects it automatically; nothing is
  hardcoded to the demo schema.
- **Connect via a filename on the server** — for a SQLite file that's
  already sitting on the machine running the backend rather than one
  you want to upload from the browser. Restricted to
  `backend/data/local_sources/` — drop the file there first, then enter
  just its filename. This is deliberately not "enter any path" (an
  arbitrary server-side path would let a signed-in user read any
  SQLite-formatted file the backend process can access); see
  `sources.connect_sqlite_path()` for the exact boundary.
- **Connect PostgreSQL / MySQL** — enter host, port, database, user, and
  password for a live server.

You can switch sources anytime from the database selector in the top
right of the query screen ("Switch database…").

## 5. Try it

Ask things like:

- "Show top 5 products by total sales amount."
- "List customers who placed more than 3 orders."
- "Add a new customer named Priya Sharma from Delhi."
- "Delete the order with id 42."

(Adjust to whatever schema you've actually connected — these examples
assume the demo database.) Every query is generated fresh by the LLM and
validated against the real, live schema before it ever touches the
database — nothing in the results panel is mocked.

## Table descriptions (the "meta table")

Right after you connect a database — demo, uploaded, or a live server —
you land on a one-time review screen instead of going straight to the
dashboard:

1. The backend introspects the schema (tables, columns, real FK
   constraints) and, in a **single batched LLM call** (not one call per
   table), asks the model for a short plain-English description of what
   each table represents.
2. Those go into a small local SQLite store scoped per
   (user, database name) — `backend/app/schema_meta.py` — separate from
   the connected database itself, same reasoning as `history.py`:
   switching data sources should never risk writing an extra table into
   someone's real database.
3. You see a review form — table name, generated description, an edit
   button. **Nothing here is mandatory.** Hit "Save & Continue"
   immediately and you're in the dashboard exactly as before; edit
   anything you want first and it's saved as you go.
4. From then on, `llm._build_schema_context()` folds both the
   descriptions and the real FK relationships into the prompt sent to
   the model on every query — a table like `trx_hdr` with no obvious
   name now comes with the context "Stores customer purchase invoices
   generated after checkout" attached, which is exactly the kind of
   schema that trips up text-to-SQL systems relying on table names
   alone.

A few deliberate choices here, worth being explicit about:

- **Reconnecting to an already-described database skips regeneration.**
  If descriptions already exist for that exact database name, the
  review screen just shows them — no repeat LLM call and no repeat
  wait for something that hasn't changed.
- **Manual edits always win.** A description you've hand-edited is
  flagged `is_custom` and is never silently overwritten by a later
  "Regenerate" — regeneration only replaces the rows the model
  generated, never the ones you corrected. This is the human-in-the-loop
  half of the design: the model gives a first draft, you can correct
  business semantics it can't infer from column names alone (e.g. "this
  is a checkout invoice", not just "a transaction record").
- **You can revisit this anytime** from the Schema tab
  (`TableDescriptions.jsx`), not just on first connect — generate, edit,
  or clear any table's description mid-session, without reconnecting.
- Reachable directly via `GET/POST/PUT/DELETE /api/schema/descriptions*`
  if you want to script it.

## Safety model

Every generated statement passes through `backend/app/sql_guard.py`
before it can run: single-statement only (blocks `;`-chained injection),
no embedded SQL comments, and every referenced table is checked against
the real, live schema of whichever source is connected.

That check alone isn't enough for statements that change data, though —
so on top of it:

- **SELECT** queries execute immediately; there's nothing to undo.
- **INSERT / UPDATE / DELETE / DDL** queries are generated and validated,
  but **not executed**. The backend returns the validated SQL with
  `pending_confirmation: true` (`POST /api/query`), the frontend shows it
  in a confirmation dialog (`ConfirmWriteModal.jsx`), and the query only
  runs after the user explicitly confirms — via a separate endpoint
  (`POST /api/query/confirm`) that re-validates the SQL from scratch
  before executing it. Nothing is committed on the strength of the first
  request alone.
- **UPDATE and DELETE must include a real WHERE clause.** Any UPDATE or
  DELETE with no WHERE clause — or a trivially-true one like `WHERE 1=1`
  — is rejected by `sql_guard.py` before it ever reaches the
  confirmation dialog, not just discouraged. This check is join-aware:
  a multi-table `UPDATE ... JOIN ... SET ...` or `DELETE ... USING ...`
  still has to carry a WHERE clause, and every table pulled in through a
  JOIN is validated against the live schema exactly like a SELECT's
  JOINs are. The system prompt sent to the model also states this
  requirement up front, so a compliant query is usually generated on the
  first try rather than needing the validator's retry loop.

Worth calling out honestly rather than overclaiming: the WHERE-clause
check is syntactic, not semantic — it confirms a WHERE clause exists and
isn't a no-op, not that it scopes to a small or "reasonable" number of
rows. A `DELETE ... USING` whose WHERE clause is only the join predicate
(e.g. `WHERE o.customer_id = c.customer_id`, no further filter) passes
this check but could still match many rows — the join match itself.
Genuinely detecting "will this touch too many rows" would require an
`EXPLAIN` against the live database, which isn't implemented here.

## Remaining known limitations, by design

- **Single-process state for data sources and rate limiting.** Active
  data sources (`app/sources.py`) and login rate-limit counters
  (`app/auth.py`) live in memory, keyed per username — two different
  users (or the same user in two tabs) each get their own isolated
  state, but both reset on a backend restart and don't sync across
  multiple backend processes behind a load balancer. Sessions themselves
  are the exception: they're SQLite-backed (`auth.db`) with a 24-hour
  expiry, so they survive a backend restart. Moving the rest to a shared
  store (Redis) is the natural next step if this ever needs to run as
  more than one process.
- **No role-based permissions** — every signed-in user has full read/write
  access to whichever database they've connected.
- **Bearer token in localStorage** rather than an httpOnly cookie — see
  the tradeoff explained in "Sign in" above and in `app/auth.py`'s
  module docstring.

## Docker deployment

The whole stack — backend, frontend, and a persistent volume for the
SQLite state — runs with Docker Compose, no local Python/Node install
required.

```bash
cp .env.example .env
# then open .env and paste in your GROQ_API_KEY

docker compose up --build
```

- Backend: `http://localhost:8000` (health check at `/api/health`)
- Frontend: `http://localhost:5173`, served by nginx from a static
  production build (not `vite dev`)

`sqlscribe-data` is a named Docker volume mounted at `/app/data` in the
backend container — `auth.db`, `history.db`, `schema_meta.db`, the
seeded demo database, and any uploaded/local SQLite files all persist
there across `docker compose down` / `up` cycles. Deleting the volume
(`docker compose down -v`) resets everything, same as deleting
`backend/data/*.db` locally.

Deploying frontend and backend on different hosts/domains? The
frontend's `VITE_API_BASE` is baked into the JS bundle at *build* time
(Vite env vars aren't a runtime thing), so set it before building:

```bash
VITE_API_BASE=https://api.yourdomain.com docker compose up --build
```

or pass it directly to `docker build --build-arg VITE_API_BASE=... ./frontend`
if you're building the frontend image on its own. Each service also has
its own standalone `Dockerfile` (`backend/Dockerfile`,
`frontend/Dockerfile`) if you'd rather build/push/run them independently
of Compose — e.g. onto separate hosts, or into an existing orchestration
setup.

## Project structure

```
sqlscribe/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI pipeline (pytest + Vitest + build)
├── docker-compose.yml
├── .env.example                 # GROQ_API_KEY etc. for docker-compose
├── backend/
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py         # FastAPI routes: auth, data sources, query + confirm, table descriptions, CORS
│   │   ├── auth.py         # signup/login, bcrypt hashing, bearer-token sessions, login + query rate limiting
│   │   ├── sources.py      # active data source: demo / uploaded sqlite / postgres / mysql — real FK & PK introspection, query timeouts, secret redaction
│   │   ├── session_store.py # per-user connection-state store (sources.py's actual backing store, not a parallel abstraction)
│   │   ├── database.py     # demo dataset schema + seed data
│   │   ├── history.py      # query history, independent of active source
│   │   ├── schema_meta.py  # table/column-description "meta table" store
│   │   ├── llm.py          # Groq API calls — question -> SQL, and schema -> table/column descriptions (capped, FK-reconciled)
│   │   └── sql_guard.py    # SQL validation / safety guardrails
│   ├── evals/
│   │   └── eval_sql.py     # SQL generation accuracy eval harness (20 benchmark questions against RetailDB)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── src/
    │   ├── test/
    │   │   └── setup.js                # Vitest + Testing Library setup
    │   ├── components/
    │   │   ├── AuthScreen.jsx          # sign-up / sign-in
    │   │   ├── DataSourceLanding.jsx   # data source picker
    │   │   ├── DatabasePrepLoading.jsx # post-connect loading screen — performs the real schema fetch, not a cosmetic timer
    │   │   ├── DescribeModal.jsx       # table/column description review modal — generate, click-to-edit, real FK/PK badges
    │   │   ├── MetaTableReview.jsx     # thin DescribeModal wrapper used right after connecting
    │   │   ├── ErrorBoundary.jsx       # catches render errors app-wide, wraps <App/> in main.jsx
    │   │   ├── Sidebar.jsx             # nav + live schema explorer
    │   │   ├── QueryPanel.jsx          # question input + SQL terminal
    │   │   ├── ConfirmWriteModal.jsx   # confirmation dialog for write queries (alertdialog, focus-on-open, Escape-to-cancel)
    │   │   ├── ConnectionStatus.jsx    # live backend health indicator
    │   │   ├── DatabaseSelector.jsx    # shows active DB, switch-database flow
    │   │   ├── ResultsPanel.jsx        # results table + CSV export
    │   │   ├── QueryHistory.jsx        # recent queries, click to re-run
    │   │   ├── HistoryView.jsx         # full history page (History tab)
    │   │   ├── SchemaView.jsx          # full schema page (Schema tab)
    │   │   ├── TableDescriptions.jsx   # thin DescribeModal wrapper used on the Schema tab
    │   │   ├── Toast.jsx               # toast notifications (role="status", aria-live="polite")
    │   │   ├── ERDiagram.jsx           # live-computed entity relationship diagram
    │   │   └── __tests__/              # component-level Vitest suites (render the real components, not copies of their logic)
    │   ├── lib/
    │   │   ├── api.js                  # backend fetch calls
    │   │   ├── columnMetadata.js       # PK & FK badge detection — real schema data first, naming convention as fallback
    │   │   ├── schemaRelationships.js  # real FK-based relationships, naming-convention fallback
    │   │   └── highlightSql.js         # SQL keyword highlighting
    │   ├── App.jsx
    │   └── index.css
    ├── tailwind.config.js          # Paper Terminal palette
    └── package.json
```

## Security & hardening

- **Rate limiting** — both `/api/query` and `/api/query/confirm` share one per-user limit (`auth.check_query_rate_limit`, 30 requests/minute by default) — each is a real, billed Groq call or a real write, so a tight client-side loop is either a bug or someone deliberately running up cost. Returns `429` with a `Retry-After` header.
- **Query timeouts** — a generated query is untrusted from the model's perspective; `SQLSCRIBE_QUERY_TIMEOUT_SECONDS` (default 25) bounds how long any single query is allowed to run, enforced via SQLite's progress-handler mechanism, Postgres `statement_timeout`, or MySQL `MAX_EXECUTION_TIME` depending on the connected dialect.
- **Secret redaction** — `sources.redact_for_user()` strips a connected Postgres/MySQL password out of any error message before it reaches the browser; applied at both connect-time (a failed connection attempt) and query-time (a failed query against an already-connected source).
- **CORS via `ALLOWED_ORIGINS`** — comma-separated env var, falls back to the standard local Vite ports if unset.
- **Session store seam** — `sources.py`'s per-user connection state goes through `session_store.py`'s get/set interface rather than a bare module-level dict, marking the exact seam a Redis-backed store would replace for a multi-instance deployment.
- **Frontend error boundary** — `ErrorBoundary.jsx` wraps the whole app in `main.jsx`, so a render error in one component shows a recoverable fallback screen instead of a blank white page.
- **Accessibility** — `ConfirmWriteModal` uses `role="alertdialog"`, `aria-labelledby`/`aria-describedby`, focuses the (safe) Cancel button on open, and closes on Escape; `Toast` uses `role="status"`/`aria-live="polite"` so screen readers announce new toasts without stealing focus.

⚠️ **If you're the original owner of this project**: an earlier version of `backend/.env` / `.env.example` had a real Groq API key committed to it. It's been replaced with a placeholder here, but if that key was ever pushed anywhere or shared, rotate it now at [console.groq.com/keys](https://console.groq.com/keys) — replacing the text in this repo does not undo any prior exposure.

## Testing & Evaluation

### Backend pytest suite

Covers SQL validation (`sql_guard.py`), auth and login/query rate-limiting, query statement timeouts, secret redaction, the session-store seam, per-user isolation of history and data sources, real primary & foreign-key introspection, and the table/column-description store — including FK-column description reconciliation and the table-count cap:

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

**141 tests**, no network calls, no external database required — everything runs against temp SQLite files and a real in-process FastAPI instance created fresh per test. `tests/test_hardening.py` and `tests/test_eval_harness.py` specifically cover the security/robustness pass described above.

### Frontend Vitest suite

Covers primary/foreign-key badge computation (`columnMetadata.js`), ER diagram relationship calculation (`schemaRelationships.js`), and `DescribeModal.jsx`/`DatabasePrepLoading.jsx` — the component tests render the actual components via React Testing Library and only mock the network boundary (`../lib/api`), rather than testing a copy of a component's logic in isolation:

```bash
cd frontend
npm install
npm test
```

**21 tests** passing, full DOM environment via `jsdom`.

### SQL generation evaluation harness

Runs 20 benchmark questions against the real Groq model (requires `GROQ_API_KEY`), executes both the generated SQL and a hand-written gold-standard query against a freshly-seeded RetailDB, and reports syntax-validation rate, execution-success rate, and exact-match rate against the gold query's results:

```bash
cd backend
python -m evals.eval_sql
```

## Notes

- The model used is `llama-3.3-70b-versatile` on Groq by default —
  override with `SQLSCRIBE_MODEL` in `backend/.env` for a different one.
  The same model and env var handle both SQL generation and table
  description generation.
- To reset the demo data, delete `backend/data/sqlscribe.db` and
  reconnect via "Load Demo Database" — it reseeds automatically. Table
  descriptions live separately in `backend/data/schema_meta.db` and
  aren't affected by this.
- Uploaded SQLite files are stored in `backend/data/uploads/`.
