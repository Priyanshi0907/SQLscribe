# ✍️ SQLscribe — Text-to-SQL Assistant

> Ask database questions in plain English and receive instant, dialect-aware, validated SQL with live interactive query results, visual ER diagrams, and query history.

![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18.3-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Groq API](https://img.shields.io/badge/Groq_API-Llama_3.3_70B-f34e3a?style=for-the-badge&logo=groq&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

---

### 🎨 Paper Terminal Theme Preview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ✍️  SQLscribe  [ RetailDB (SQLite) ] [ 🟢 Backend Online ] [ Switch DB... ] │
├─────────────────────────────────────────────────────────────────────────────┤
│ 💬 Question: "Show top 5 customers by total order spend"                   │
│                                                                             │
│ 💻 Generated & Validated SQL                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ SELECT c.customer_id, c.name, SUM(o.total_amount) AS total_spend       │ │
│ │ FROM customers c                                                        │ │
│ │ JOIN orders o ON c.customer_id = o.customer_id                          │ │
│ │ GROUP BY c.customer_id, c.name                                          │ │
│ │ ORDER BY total_spend DESC                                               │ │
│ │ LIMIT 5                                                                 │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ 📊 Results (5 rows, 14ms) [ 📥 Export CSV ]                                │
│ ┌─────────────┬──────────────────┬──────────────┐                           │
│ │ customer_id │ name             │ total_spend  │                           │
│ ├─────────────┼──────────────────┼──────────────┤                           │
│ │ 104         │ Eleanor Vance    │ 4250.00      │                           │
│ │ 112         │ Marcus Sterling  │ 3890.50      │                           │
│ │ 205         │ Sophia Chen      │ 3410.20      │                           │
│ └─────────────┴──────────────────┴──────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📖 Overview

**SQLscribe** is an enterprise-grade, full-stack Text-to-SQL query assistant designed to democratize database access. By coupling a fast **FastAPI** backend with a high-performance **React 18** interface, SQLscribe allows non-technical stakeholders and developers alike to query complex databases in plain English without writing a single line of SQL manually.

Under the hood, SQLscribe leverages the **Groq API (Llama 3.3 70B)** for dialect-aware SQL generation, paired with real-time **database schema introspection** and **AST-based SQL guardrails** (`sqlglot`) to guarantee that every generated query is syntactically sound, schema-valid, and execution-safe.

---

## ❓ Problem Statement

In modern data-driven organizations:
1. **High Barrier to Entry**: Business analysts, product managers, and decision-makers often lack deep SQL expertise (joins, window functions, CTEs), creating reliance on overloaded engineering teams.
2. **Schema Hallucination in Naive LLMs**: Standard text-to-SQL prompts frequently hallucinate non-existent table and column names or produce syntax incompatible with specific database engines (e.g. SQLite vs. PostgreSQL vs. MySQL).
3. **Security & Injection Risks**: Unchecked LLM SQL generation can lead to catastrophic data loss via destructive operations (`DROP TABLE`, un-indexed `UPDATE` / `DELETE`) or SQL injection vulnerabilities (`SELECT ...; DROP DATABASE;`).

---

## 💡 Solution

SQLscribe introduces a **Human-in-the-Loop, Guardrailed AI Architecture**:
- **Live Schema Introspection**: Fetches exact table structures, column definitions, and data types directly from the active database before prompting the LLM.
- **Dialect-Specific Prompting**: Dynamically instructs the LLM to format SQL for SQLite, PostgreSQL, or MySQL.
- **Abstract Syntax Tree (AST) Validation Engine**: Intercepts every generated query with `sqlglot` to enforce single-statement constraints, block SQL comment injection, verify table references against allowed schemas, and confirm read-only safety.
- **Self-Correcting LLM Retry Loop**: If a query fails validation, the validator's error message is automatically fed back to Llama 3.3 for immediate self-correction.

---

## ✨ Features

- 🔌 **Hot-Swappable Data Sources**:
  - **Seeded Demo Database**: Instant setup with an e-commerce RetailDB schema (`customers`, `products`, `orders`, `order_items`).
  - **SQLite File Upload**: Upload any custom `.db` / `.sqlite` file for automatic schema parsing.
  - **Local SQLite Path**: Connect directly to any local SQLite file path.
  - **Live PostgreSQL Server**: Connect directly to remote or local PostgreSQL instances.
  - **Live MySQL Server**: Connect directly to remote or local MySQL instances.
- 🤖 **Groq Llama 3.3 70B Engine**: Sub-second natural language translation tuned specifically for SQL generation.
- 🛡️ **SQL Guard Safety System**: AST-based validation preventing multi-statement execution, comments, unknown table references, and unwanted mutations.
- 🎨 **Paper Terminal Interface**: Minimalist warm paper backdrop (`#FAF7F1`) paired with a high-contrast dark terminal window (`#2B2B2B`) for crisp SQL code visibility.
- 📊 **Interactive Results Grid**: Automatic column deduplication, row-capping (500 max rows protection), and instant CSV data export.
- 🗺️ **Live ER Diagram Generator**: Interactive, dynamically computed entity-relationship visualizer built from live schema introspection.
- 📜 **Execution History & Favorites**: Persisted query history per database, favorite query bookmarking, and one-click query re-run.
- 🔐 **Token Authentication**: Built-in signup, login, and bearer-token session protection powered by bcrypt password hashing.

---

## 🏗 Architecture

The following diagram illustrates SQLscribe's multi-tiered system architecture, data flow, and component interactions:

```mermaid
flowchart TD
    subgraph Client ["💻 Client Tier (React 18 + Tailwind)"]
        UI["Paper Terminal Web App"]
        UI_Components["- Data Source Picker<br/>- Query & Terminal Panel<br/>- Results Grid & CSV Export<br/>- Live ER Diagram<br/>- Query History & Favorites"]
    end

    subgraph Hosting ["🚀 FastAPI Backend Service"]
        API["FastAPI App (Uvicorn Engine)"]
        AuthModule["Auth Module (Bcrypt + Sessions)"]
        SourceModule["Source Introspector & Driver"]
        GuardModule["SQL Guard (sqlglot AST Validator)"]
        HistoryModule["History Store Manager"]
    end

    subgraph AILayer ["🤖 AI Generation Layer"]
        GroqAPI["Groq API (Llama 3.3 70B)"]
    end

    subgraph DataLayer ["🗄️ Active Data Source (Connected DB)"]
        DemoDB["Seeded Demo RetailDB (SQLite)"]
        UploadDB["Uploaded SQLite (.db / .sqlite)"]
        PostgresDB["Live PostgreSQL Server"]
        MySQLDB["Live MySQL Server"]
    end

    subgraph InternalStorage ["💾 System Persistence"]
        AuthDB[("Auth DB (auth.db)")]
        HistDB[("History DB (history.db)")]
    end

    %% Component Data Flows
    UI -->|HTTP / REST API| API
    API --> AuthModule
    AuthModule --> AuthDB
    
    API -->|1. Introspect Schema| SourceModule
    SourceModule --> DataLayer
    
    API -->|2. Question + Live Schema| GroqAPI
    GroqAPI -->|3. Generated Raw SQL| API
    
    API -->|4. Validate AST & Security| GuardModule
    GuardModule -->|5. Validated Safe SQL| API
    
    API -->|6. Execute Safe Query| DataLayer
    DataLayer -->|7. Result Sets & Metadata| API
    
    API -->|8. Log Execution History| HistoryModule
    HistoryModule --> HistDB
    
    API -->|9. JSON Response (SQL, Data, ER)| UI
```

### Architectural Component Breakdown

- **App / Client Tier (React 18)**: Single-page application designed with the Paper Terminal aesthetic. Handles data source selection, prompt submission, syntax-highlighted SQL rendering, interactive table views with CSV export, dynamic ER diagram visualization, and user sessions.
- **API Layer (FastAPI)**: Asynchronous Python REST service serving as the core orchestrator. Manages connection pooling, endpoint routing, session authentication, and database metadata extraction.
- **AI Layer (Groq API)**: Powered by `llama-3.3-70b-versatile`. Formulates dialect-aware SQL prompts by appending live table/column schema context, enforcing single statement responses without markdown noise.
- **Parsing & Guardrail Layer (`sqlglot` + `sql_guard.py`)**: Intercepts LLM outputs before execution. Parses raw text into Abstract Syntax Trees (AST), verifies referenced tables against the live schema, strips comment tokens, blocks multi-statement injection, and enforces read-only execution modes.
- **Data Tier (Hot-Swappable Connectors)**: Database abstraction layer providing zero-config SQLite seeding, uploaded `.db` file parsing, and connection management for live PostgreSQL (`psycopg2`) and MySQL (`pymysql`) instances.
- **Persistence Store**: Independent SQLite database instances handling user authentication tokens (`auth.db`) and user query execution logs (`history.db`) isolated from active user data sources.

---

## 🛡 AI Guardrails

SQLscribe enforces strict multi-layered AI safety mechanisms before any generated query hits a database:

1. **AST Parsing (`sqlglot`)**: Converts LLM-generated string outputs into structured Abstract Syntax Trees to verify syntax correctness across dialect targets (`sqlite`, `postgres`, `mysql`).
2. **Multi-Statement Injection Prevention**: Rejects any query containing semicolon `;` execution separators to block nested or piggybacked SQL attacks.
3. **SQL Comment Stripping**: Rejects `--`, `/*`, and `*/` comment syntax to prevent comment-based logic bypasses.
4. **Schema Boundary Enforcement**: Extracted table names from the AST are validated against `allowed_tables` retrieved from live schema introspection. Any query referencing unknown or unmapped tables is blocked immediately.
5. **Read-Only Enforcer**: Detects query types (`exp.Select`) and rejects unauthorized DDL/DML statements unless write permissions are explicitly enabled.
6. **Automatic LLM Self-Correction**: When AST validation fails, SQLscribe passes the validation error back to Llama 3.3 for a second attempt, allowing the LLM to self-correct its query syntax or table names automatically.
7. **Memory Protection & Deduplication**: Enforces a strict 500-row return limit (`MAX_ROWS`) and automatically deduplicates repeating result column names (`name`, `name_2`) to prevent data loss or frontend memory crashes.

---

## 🛠 Tech Stack

| Domain | Technology / Library | Description |
| :--- | :--- | :--- |
| **Frontend Framework** | React 18, Vite | High-performance SPA frontend |
| **Styling & UI** | Tailwind CSS, Framer Motion | Paper Terminal custom palette & smooth UI transitions |
| **Icons & Visuals** | Lucide React | Clean, scalable vector iconography |
| **Backend Framework** | FastAPI, Uvicorn | Async Python ASGI web framework |
| **LLM Provider** | Groq API (`llama-3.3-70b-versatile`) | Ultra-low latency natural language to SQL translation |
| **SQL Parser & Validator**| `sqlglot` | AST construction, SQL dialect translation, & guardrails |
| **Database Connectors** | SQLite (`sqlite3`), PostgreSQL (`psycopg2-binary`), MySQL (`pymysql`) | Native multi-engine database support |
| **Authentication** | Passlib, Bcrypt, PyJWT | Secure user signup, password hashing, and session management |

---

## ⚙️ Installation

### Prerequisites

Ensure you have the following installed on your machine:
- **Python 3.10+**
- **Node.js 18+** & **npm**
- **Groq API Key**: Obtain a free key from [Groq Console](https://console.groq.com/keys)

---

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
```

Open `.env` and set your Groq API key:
```env
GROQ_API_KEY=your_groq_api_key_here
SQLSCRIBE_MODEL=llama-3.3-70b-versatile
```

Start the backend server:
```bash
uvicorn app.main:app --reload --port 8000
```

Verify backend health:
```bash
curl http://127.0.0.1:8000/api/health
# Response: {"status":"ok"}
```

---

### 2. Frontend Setup

In a separate terminal window:

```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

Open your browser and visit: `http://localhost:5173`

---

## 🚀 Usage

1. **Sign Up / Log In**: Create an account on the initial authentication screen.
2. **Select Data Source**:
   - **Load Demo Database**: Seeds an instant e-commerce database with zero setup.
   - **Upload SQLite Database**: Select any `.db` or `.sqlite` file from your computer.
   - **Connect PostgreSQL / MySQL**: Input database host, port, database name, user, and password.
3. **Ask Questions**: Type natural language prompts like:
   - *"Show top 5 products by total sales revenue."*
   - *"List all customers who placed more than 3 orders."*
   - *"Calculate average order value by product category."*
4. **Inspect & Export**:
   - View the generated SQL in the dark Paper Terminal panel.
   - Browse query results in the table grid and export to CSV.
   - Click the **Schema** tab to explore tables or view the dynamically generated **ER Diagram**.
   - Click the **History** tab to re-run or favorite previous queries.

---

## 📂 Project Structure

```
sqlscribe/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI endpoints (Auth, Sources, Schema, Query, History)
│   │   ├── auth.py          # User authentication, password hashing & session management
│   │   ├── sources.py       # Active data source manager (Demo, SQLite, Postgres, MySQL)
│   │   ├── database.py      # Seed schema definition & demo RetailDB seeder
│   │   ├── history.py       # Query execution logger & favorites persistence
│   │   ├── llm.py           # Groq API client & dialect-aware prompt generation
│   │   └── sql_guard.py     # sqlglot AST parsing, SQL validation & security guardrails
│   ├── data/                # System databases (auth.db, history.db, demo database)
│   ├── requirements.txt     # Python backend dependencies
│   └── .env.example         # Environment template for Groq API key
│
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── DataSourceLanding.jsx # Initial data source selection view
    │   │   ├── Sidebar.jsx           # Sidebar navigation & live schema explorer
    │   │   ├── QueryPanel.jsx        # Question input & terminal-style SQL panel
    │   │   ├── ConnectionStatus.jsx  # Live backend connection indicator
    │   │   ├── DatabaseSelector.jsx  # Active database display & switcher modal
    │   │   ├── ResultsPanel.jsx      # Interactive data table & CSV exporter
    │   │   ├── QueryHistory.jsx      # Recent query history drawer
    │   │   ├── HistoryView.jsx       # Full execution history view with search
    │   │   ├── SchemaView.jsx        # Detailed schema viewer tab
    │   │   └── ERDiagram.jsx         # Live entity-relationship visualizer
    │   ├── lib/
    │   │   ├── api.js                # Frontend API client & fetch wrappers
    │   │   └── highlightSql.js       # SQL keyword syntax highlighter
    │   ├── App.jsx                   # Main application state & tab router
    │   └── index.css                 # Base styles & Paper Terminal custom palette
    ├── tailwind.config.js            # Tailwind configuration & color tokens
    └── package.json                  # Frontend dependencies & scripts
```

---

## 🔮 Future Enhancements

- 👤 **Per-User Database Connections**: Isolate active database sessions per user session token rather than process-wide global state.
- ✍️ **Controlled Write Operations**: Interactive confirmation dialogs for safe `INSERT` / `UPDATE` queries with enforced `WHERE` clause checks.
- 📈 **Automated Chart Generation**: Built-in charting (Bar charts, Line graphs, Pie charts) powered by Recharts/Chart.js for numeric query results.
- 💡 **AI Response Insights**: Generative text summaries explaining the data insights alongside raw query table output.
- ⚡ **EXPLAIN ANALYZE Integration**: Visual query execution plan and performance optimization recommendations.

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork the Repository**
2. **Create a Feature Branch**: `git checkout -b feature/AmazingFeature`
3. **Commit your Changes**: `git commit -m 'Add some AmazingFeature'`
4. **Push to the Branch**: `git push origin feature/AmazingFeature`
5. **Open a Pull Request**

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
