# SQLscribe — Text-to-SQL Assistant

Ask a database questions in plain English and get back real, validated SQL
plus live results. Built with a FastAPI backend, a React + Tailwind
frontend, and the Gemini API for natural language → SQL generation.

You choose your data source on first load — a seeded demo database, your
own uploaded SQLite file, or a live PostgreSQL server.

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
  - Lets you connect one of three data sources: a seeded demo SQLite
    database ("RetailDB"), an uploaded `.db`/`.sqlite` file, or a live
    PostgreSQL server (see `app/sources.py`)
  - Introspects whichever database is active and sends that live schema
    to the Gemini API to generate SQL — dialect-aware (SQLite vs
    PostgreSQL), never hardcoded to one schema
  - Validates every generated query before running it (single statement,
    SELECT-only, only references tables that actually exist — see
    `app/sql_guard.py`)
  - Executes the query and returns results, logging each one to a
    separate local history store (`app/history.py`) that's independent
    of whichever data source is active
- **Frontend** (`/frontend`) — React app matching the Paper Terminal
  design: a data-source picker on first load, then the query interface —
  question box, terminal-style generated-SQL panel with syntax
  highlighting, results table with CSV export, a live ER diagram in the
  Schema tab, and query history.

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Gemini API key: https://aistudio.google.com/apikey
- (Optional) A PostgreSQL server, only if you want to connect a live
  database instead of the demo or an uploaded SQLite file

## 1. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then open .env and paste in your GEMINI_API_KEY

uvicorn app.main:app --reload --port 8000
```

Confirm it's running:
```bash
curl http://127.0.0.1:8000/api/health
```
Should return `{"status":"ok"}`. Nothing is auto-loaded at startup —
you pick a data source from the UI on first load.

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

## 3. Pick a data source

On first load you'll see three options:

- **Load Demo Database** — instant, seeds a small retail dataset
  (customers, products, orders, order_items) with zero setup.
- **Upload SQLite Database** — pick any `.db`/`.sqlite` file with real
  tables in it. The app introspects it automatically; nothing is
  hardcoded to the demo schema.
- **Connect PostgreSQL** — enter host, port, database, user, and
  password for a live server.

You can switch sources anytime from the database selector in the top
right of the query screen ("Switch database…").

## 4. Try it

Ask things like:

- "Show top 5 products by total sales amount."
- "List customers who placed more than 3 orders."
- "Show total revenue by product category."
- "Which orders are still pending?"

(Adjust to whatever schema you've actually connected — these examples
assume the demo database.) Every query is generated fresh by the LLM,
validated, and run against real data — nothing in the results panel is
mocked.

## Safety model

This build runs in **read-only mode** by default: the validator
(`backend/app/sql_guard.py`) rejects anything that isn't a single SELECT
statement, blocks multi-statement injection, and checks every referenced
table against the real, live schema of whichever source is connected —
before execution.

To extend this into INSERT/UPDATE support:
1. Allow those statement types in `ALLOWED_STATEMENT_TYPES` in `sql_guard.py`.
2. Add a required confirmation step in the UI before any write executes.
3. Enforce a `WHERE` clause on every UPDATE before allowing execution.
4. Add role-based permissions if more than one user will use the tool.

## A known limitation, by design

The active data source is a single **process-wide** value, not
per-session — fine for one person using this as a demo, but if two
people opened it in separate browser tabs at once, they'd be sharing
(and overwriting) the same connection. Turning this into proper
per-session state would mean keying the active source by a session or
user id instead of a single global in `app/sources.py`.

## Project structure

```
sqlscribe/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI routes, incl. data-source endpoints
│   │   ├── sources.py     # active data source: demo / uploaded sqlite / postgres
│   │   ├── database.py    # demo dataset schema + seed data
│   │   ├── history.py     # query history, independent of active source
│   │   ├── llm.py         # Gemini API call — question -> SQL, dialect-aware
│   │   └── sql_guard.py   # SQL validation / safety guardrails
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── DataSourceLanding.jsx  # first-load data source picker
    │   │   ├── Sidebar.jsx            # nav + live schema explorer
    │   │   ├── QueryPanel.jsx         # question input + SQL terminal
    │   │   ├── ConnectionStatus.jsx   # live backend health indicator
    │   │   ├── DatabaseSelector.jsx   # shows active DB, switch-database flow
    │   │   ├── ResultsPanel.jsx       # results table + CSV export
    │   │   ├── QueryHistory.jsx       # recent queries, click to re-run
    │   │   ├── HistoryView.jsx        # full history page (History tab)
    │   │   ├── SchemaView.jsx         # full schema page (Schema tab)
    │   │   └── ERDiagram.jsx          # live-computed entity relationship diagram
    │   ├── lib/
    │   │   ├── api.js             # backend fetch calls
    │   │   └── highlightSql.js    # SQL keyword highlighting
    │   ├── App.jsx
    │   └── index.css
    ├── tailwind.config.js         # Paper Terminal palette
    └── package.json
```

## Notes

- The model used is `gemini-flash-latest` by default — override with
  `SQLSCRIBE_MODEL` in `backend/.env` for a pinned version.
- To reset the demo data, delete `backend/data/sqlscribe.db` and
  reconnect via "Load Demo Database" — it reseeds automatically.
- Uploaded SQLite files are stored in `backend/data/uploads/`.
