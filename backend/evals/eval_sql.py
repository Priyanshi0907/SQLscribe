"""
Evaluation Harness for SQLscribe Natural Language -> SQL Generation.

Evaluates LLM generation accuracy across 20 benchmark questions against RetailDB.
Measures:
  1. Syntax & Guard Validation Rate
  2. Execution Success Rate against SQLite
  3. Result Set Content / Row Count Accuracy vs Gold SQL
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app import database as demo_db
from app import schema_meta
from app import sources
from app.llm import generate_sql
from app.sql_guard import validate_sql

BENCHMARK_QUESTIONS = [
    {
        "id": 1,
        "question": "Show all products in the Electronics category.",
        "gold_sql": "SELECT * FROM products WHERE category = 'Electronics'",
    },
    {
        "id": 2,
        "question": "How many total customers are in the database?",
        "gold_sql": "SELECT COUNT(*) FROM customers",
    },
    {
        "id": 3,
        "question": "List all orders placed in January 2024.",
        "gold_sql": "SELECT * FROM orders WHERE order_date >= '2024-01-01' AND order_date < '2024-02-01'",
    },
    {
        "id": 4,
        "question": "Find the top 5 most expensive products.",
        "gold_sql": "SELECT * FROM products ORDER BY price DESC LIMIT 5",
    },
    {
        "id": 5,
        "question": "What is the total stock quantity of all products?",
        "gold_sql": "SELECT SUM(stock_quantity) FROM products",
    },
    {
        "id": 6,
        "question": "Show customer names along with their order IDs.",
        "gold_sql": "SELECT c.name, o.order_id FROM customers c JOIN orders o ON c.customer_id = o.customer_id",
    },
    {
        "id": 7,
        "question": "Find products with price greater than 50.",
        "gold_sql": "SELECT * FROM products WHERE price > 50",
    },
    {
        "id": 8,
        "question": "Count how many orders each customer has placed.",
        "gold_sql": "SELECT customer_id, COUNT(*) AS order_count FROM orders GROUP BY customer_id",
    },
    {
        "id": 9,
        "question": "What is the average price of products by category?",
        "gold_sql": "SELECT category, AVG(price) AS avg_price FROM products GROUP BY category",
    },
    {
        "id": 10,
        "question": "List orders with status 'completed'.",
        "gold_sql": "SELECT * FROM orders WHERE status = 'completed'",
    },
    {
        "id": 11,
        "question": "Find total quantity sold per product in order_items.",
        "gold_sql": "SELECT product_id, SUM(quantity) AS total_sold FROM order_items GROUP BY product_id",
    },
    {
        "id": 12,
        "question": "Show the cheapest product.",
        "gold_sql": "SELECT * FROM products ORDER BY price ASC LIMIT 1",
    },
    {
        "id": 13,
        "question": "List orders sorted by total_amount descending.",
        "gold_sql": "SELECT * FROM orders ORDER BY total_amount DESC",
    },
    {
        "id": 14,
        "question": "Find customers located in 'New York'.",
        "gold_sql": "SELECT * FROM customers WHERE city = 'New York'",
    },
    {
        "id": 15,
        "question": "Show products where stock_quantity is less than 10.",
        "gold_sql": "SELECT * FROM products WHERE stock_quantity < 10",
    },
    {
        "id": 16,
        "question": "Get total revenue across all completed orders.",
        "gold_sql": "SELECT SUM(total_amount) FROM orders WHERE status = 'completed'",
    },
    {
        "id": 17,
        "question": "Find order items where unit_price exceeds 100.",
        "gold_sql": "SELECT * FROM order_items WHERE unit_price > 100",
    },
    {
        "id": 18,
        "question": "List products with product_name containing 'Phone'.",
        "gold_sql": "SELECT * FROM products WHERE product_name LIKE '%Phone%'",
    },
    {
        "id": 19,
        "question": "Count total order items.",
        "gold_sql": "SELECT COUNT(*) FROM order_items",
    },
    {
        "id": 20,
        "question": "Show all columns from order_items with quantity > 2.",
        "gold_sql": "SELECT * FROM order_items WHERE quantity > 2",
    },
]


def run_eval(username: str = "eval_user"):
    # generate_sql() looks up this user's active connection through
    # sources.py (the same lookup /api/query goes through) — without
    # actually registering "eval_user" as connected via connect_demo(),
    # every single call below would immediately fail with
    # sources.SourceError("No data source connected yet."), which is
    # exactly the bug that made this script crash before it ever got to
    # printing a single result. init_db() ensures the seeded demo
    # database file actually exists on disk before anything opens it.
    demo_db.init_db()
    sources.connect_demo(username)
    # generate_sql() -> _build_schema_context() also reads from
    # schema_meta.py's own SQLite file (separate from the demo database)
    # to fold in any saved table/column descriptions. On a fresh clone
    # that file doesn't exist yet — normally main.py's startup lifespan
    # creates it, but this script runs standalone and never goes through
    # that lifespan, so it has to initialize it here too.
    schema_meta.init_schema_meta_db()
    conn = sqlite3.connect(demo_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    allowed_tables = {"customers", "products", "orders", "order_items"}
    passed_validation = 0
    passed_execution = 0
    exact_row_matches = 0
    total = len(BENCHMARK_QUESTIONS)

    print(f"\n=======================================================")
    print(f"  SQLscribe LLM Benchmark Evaluation ({total} questions)")
    print(f"=======================================================\n")

    for q_item in BENCHMARK_QUESTIONS:
        qid = q_item["id"]
        question = q_item["question"]
        gold_sql = q_item["gold_sql"]

        try:
            # 1. Run LLM generation
            raw_sql = generate_sql(question, username, dialect="sqlite")
            # 2. Validate with sql_guard
            safe_sql, _ = validate_sql(raw_sql, allowed_tables=allowed_tables, dialect="sqlite")
            passed_validation += 1

            # 3. Execute generated SQL
            gen_rows = conn.execute(safe_sql).fetchall()
            gold_rows = conn.execute(gold_sql).fetchall()
            passed_execution += 1

            # 4. Compare row counts
            if len(gen_rows) == len(gold_rows):
                exact_row_matches += 1
                status = "PASS [Execution & Row Match]"
            else:
                status = f"PARTIAL [Row count mismatch: gen={len(gen_rows)} vs gold={len(gold_rows)}]"

        except Exception as exc:
            status = f"FAIL [{exc}]"

        print(f"[{qid:02d}/{total:02d}] {question}")
        print(f"       Result: {status}")

    conn.close()

    print(f"\n-------------------------------------------------------")
    print(f"  Validation Success: {passed_validation}/{total} ({(passed_validation/total)*100:.1f}%)")
    print(f"  Execution Success:  {passed_execution}/{total} ({(passed_execution/total)*100:.1f}%)")
    print(f"  Exact Row Matches:  {exact_row_matches}/{total} ({(exact_row_matches/total)*100:.1f}%)")
    print(f"=======================================================\n")

    return {
        "validation_rate": passed_validation / total,
        "execution_rate": passed_execution / total,
        "match_rate": exact_row_matches / total,
    }


if __name__ == "__main__":
    run_eval()
