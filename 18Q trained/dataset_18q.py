"""
dataset_18q.py
--------------
Dataset builder and formatting module for the 18 benchmark Text-to-SQL questions
from the Project Design Report & test suite.
"""

import json
from schema_context import SCHEMA_CONTEXT

BENCHMARK_18Q = [
    {
        "id": 1,
        "question": "Show me all customers from Delhi",
        "sql": "SELECT * FROM customers WHERE city = 'Delhi';",
        "category": "SELECT / Filtering",
        "description": "Basic single-table SELECT with WHERE clause filter."
    },
    {
        "id": 2,
        "question": "List all products under 500 rupees",
        "sql": "SELECT product_name, price FROM products WHERE price < 500;",
        "category": "SELECT / Range Filter",
        "description": "Numeric comparison filter on products table."
    },
    {
        "id": 3,
        "question": "How many orders are there in total?",
        "sql": "SELECT COUNT(*) AS total_orders FROM orders;",
        "category": "SELECT / Aggregation",
        "description": "Simple table row aggregation using COUNT."
    },
    {
        "id": 4,
        "question": "Show me the top 5 customers by total orders in 2026",
        "sql": "SELECT c.name, COUNT(o.order_id) AS total_orders FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE o.order_date >= '2026-01-01' GROUP BY c.name ORDER BY total_orders DESC LIMIT 5;",
        "category": "SELECT / JOIN + GroupBy + OrderBy + Limit",
        "description": "Multi-table JOIN with aggregation, date filter, sorting, and limit."
    },
    {
        "id": 5,
        "question": "What products has customer Rahul Singh ordered?",
        "sql": "SELECT DISTINCT p.product_name FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id JOIN customers c ON o.customer_id = c.customer_id WHERE c.name = 'Rahul Singh';",
        "category": "SELECT / 4-Table JOIN",
        "description": "Complex multi-table join across customers, orders, order_items, and products."
    },
    {
        "id": 6,
        "question": "Show all orders that are still pending",
        "sql": "SELECT * FROM orders WHERE status = 'pending';",
        "category": "SELECT / Enum Filter",
        "description": "Filtering orders by string status enum."
    },
    {
        "id": 7,
        "question": "What is the total revenue by product category?",
        "sql": "SELECT p.category, SUM(p.price * oi.quantity) AS total_revenue FROM order_items oi JOIN products p ON p.product_id = oi.product_id GROUP BY p.category ORDER BY total_revenue DESC;",
        "category": "SELECT / Computed Aggregation",
        "description": "JOIN with arithmetic price multiplication and SUM aggregation grouped by category."
    },
    {
        "id": 8,
        "question": "Which product has been ordered the most?",
        "sql": "SELECT p.product_name, SUM(oi.quantity) AS total_quantity FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.product_name ORDER BY total_quantity DESC LIMIT 1;",
        "category": "SELECT / Top Aggregation",
        "description": "Group by product with SUM of quantity, ordered descending with limit 1."
    },
    {
        "id": 9,
        "question": "What is the average order value per customer?",
        "sql": "SELECT c.name, AVG(order_total) AS avg_order_value FROM customers c JOIN (SELECT o.customer_id, SUM(p.price * oi.quantity) AS order_total FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id GROUP BY o.order_id, o.customer_id) t ON c.customer_id = t.customer_id GROUP BY c.customer_id, c.name;",
        "category": "SELECT / Subquery Aggregation",
        "description": "Advanced subquery computing order totals then averaging per customer."
    },
    {
        "id": 10,
        "question": "Show customers who have never placed an order",
        "sql": "SELECT c.* FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id WHERE o.order_id IS NULL;",
        "category": "SELECT / LEFT JOIN (Anti-join)",
        "description": "LEFT JOIN with NULL check to find unlinked rows."
    },
    {
        "id": 11,
        "question": "Find the top 3 selling products in the Electronics category",
        "sql": "SELECT p.product_name, SUM(oi.quantity) AS total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id WHERE p.category = 'Electronics' GROUP BY p.product_id, p.product_name ORDER BY total_sold DESC LIMIT 3;",
        "category": "SELECT / Filtered Top Aggregation",
        "description": "Category filter combined with SUM aggregation and top-N ranking."
    },
    {
        "id": 12,
        "question": "Add a new customer named Priya from Mumbai",
        "sql": "INSERT INTO customers (name, email, city) VALUES ('Priya', 'priya@example.com', 'Mumbai');",
        "category": "INSERT / Data Creation",
        "description": "Field value extraction from natural language into INSERT statement."
    },
    {
        "id": 13,
        "question": "Add a new product called Desk Lamp in Home category priced at 599",
        "sql": "INSERT INTO products (product_name, category, price) VALUES ('Desk Lamp', 'Home', 599);",
        "category": "INSERT / Multi-field Creation",
        "description": "Extracting multiple structured entity attributes into INSERT statement."
    },
    {
        "id": 14,
        "question": "Change Rohan's order number 1042 status to delivered",
        "sql": "UPDATE orders SET status = 'delivered' WHERE order_id = 1042;",
        "category": "UPDATE / Scoped Field Edit",
        "description": "Targeted update with explicit WHERE clause on order_id."
    },
    {
        "id": 15,
        "question": "Update the price of product 5 to 999",
        "sql": "UPDATE products SET price = 999 WHERE product_id = 5;",
        "category": "UPDATE / Numeric Edit",
        "description": "Updating product record price by product_id."
    },
    {
        "id": 16,
        "question": "Delete all orders from last year",
        "sql": "ERROR: This operation is not permitted.",
        "category": "GUARDRAIL / Blocked Operation",
        "description": "DELETE queries are blocked by system guardrails."
    },
    {
        "id": 17,
        "question": "Update all customer emails",
        "sql": "ERROR: Cannot generate unscoped UPDATE/DELETE. Please specify which row(s) to modify.",
        "category": "GUARDRAIL / Missing WHERE clause",
        "description": "Unscoped UPDATE attempt blocked due to missing WHERE clause."
    },
    {
        "id": 18,
        "question": "Now filter that to only Bengaluru customers",
        "sql": "SELECT * FROM customers WHERE city = 'Bengaluru';",
        "category": "CONVERSATIONAL / Contextual Follow-up",
        "description": "Conversational turn building upon previous query context."
    }
]


def format_alpaca_dataset(dataset=BENCHMARK_18Q):
    """Formats dataset for Hugging Face Alpaca-style instruction fine-tuning."""
    records = []
    for item in dataset:
        instruction = f"Convert the following natural language question into a valid SQL query based on the database schema.\n\n{SCHEMA_CONTEXT}"
        input_text = item["question"]
        output_text = item["sql"]

        records.append({
            "instruction": instruction,
            "input": input_text,
            "output": output_text
        })
    return records


def format_chatml_dataset(dataset=BENCHMARK_18Q):
    """Formats dataset for ChatML format (OpenAI / Qwen / Llama fine-tuning)."""
    records = []
    system_prompt = f"You are a Text-to-SQL engine. Generate valid SQL for the given schema.\n\n{SCHEMA_CONTEXT}"
    for item in dataset:
        records.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": item["question"]},
                {"role": "assistant", "content": item["sql"]}
            ]
        })
    return records


def export_dataset_files():
    alpaca_data = format_alpaca_dataset()
    chatml_data = format_chatml_dataset()

    with open("dataset_18q_alpaca.json", "w") as f:
        json.dump(alpaca_data, f, indent=2)

    with open("dataset_18q_chatml.jsonl", "w") as f:
        for item in chatml_data:
            f.write(json.dumps(item) + "\n")

    print(f"Exported 18 benchmark pairs to dataset_18q_alpaca.json and dataset_18q_chatml.jsonl")


if __name__ == "__main__":
    export_dataset_files()
