"""
setup_db.py
-----------
Creates a SQLite database matching the schema + dataset sizes from the
project report (Section 3.2): 20 customers, 15 products, 36 orders,
81 order items. Run once to generate demo.db for local testing.

Run: python setup_db.py
"""

import sqlite3
import random
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "demo.db"

SCHEMA_SQL = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price DECIMAL NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
"""

FIRST_NAMES = ["Vikram", "Rahul", "Priya", "Asha", "Rohan", "Sneha", "Amit", "Neha",
               "Kunal", "Divya", "Arjun", "Pooja", "Karan", "Meera", "Vivek", "Anjali",
               "Sanjay", "Ritu", "Manish", "Kavya"]
LAST_NAMES = ["Verma", "Singh", "Iyer", "Nair", "Mehta", "Gupta", "Sharma", "Chauhan",
              "Reddy", "Kapoor"]
CITIES = ["Delhi", "Mumbai", "Bengaluru", "Pune", "Chennai", "Hyderabad", "Kolkata"]

PRODUCTS = [
    ("Wireless Mouse", "Electronics", 799.00),
    ("Mechanical Keyboard", "Electronics", 3499.00),
    ("USB-C Hub", "Electronics", 1299.00),
    ("Bluetooth Speaker", "Electronics", 1999.00),
    ("Webcam HD", "Electronics", 2199.00),
    ("Yoga Mat", "Fitness", 899.00),
    ("Dumbbell Set 10kg", "Fitness", 2499.00),
    ("Resistance Bands", "Fitness", 499.00),
    ("Desk Lamp", "Home", 599.00),
    ("Ceramic Mug Set", "Home", 349.00),
    ("Throw Blanket", "Home", 1199.00),
    ("Notebook A5", "Stationery", 149.00),
    ("Gel Pen Pack", "Stationery", 99.00),
    ("Backpack", "Accessories", 1799.00),
    ("Water Bottle", "Accessories", 449.00),
]

STATUSES = ["shipped", "delivered", "pending", "cancelled"]


def generate_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    # Customers (20)
    used_names = set()
    for i in range(1, 21):
        while True:
            fname = random.choice(FIRST_NAMES)
            lname = random.choice(LAST_NAMES)
            full_name = f"{fname} {lname}"
            if full_name not in used_names:
                used_names.add(full_name)
                break
        email = f"{fname.lower()}.{lname.lower()}{i}@example.com"
        city = random.choice(CITIES)
        conn.execute(
            "INSERT INTO customers (customer_id, name, email, city) VALUES (?, ?, ?, ?)",
            (i, full_name, email, city),
        )

    # Products (15)
    for i, (name, category, price) in enumerate(PRODUCTS, start=1):
        conn.execute(
            "INSERT INTO products (product_id, product_name, category, price) VALUES (?, ?, ?, ?)",
            (i, name, category, price),
        )

    # Orders (36)
    for i in range(1001, 1037):
        customer_id = random.randint(1, 20)
        month = random.randint(1, 7)
        day = random.randint(1, 28)
        order_date = f"2026-{month:02d}-{day:02d}"
        status = random.choice(STATUSES)
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
            (i, customer_id, order_date, status),
        )

    # Order items (81) — spread across the 36 orders
    order_ids = list(range(1001, 1037))
    item_id = 1
    for _ in range(81):
        order_id = random.choice(order_ids)
        product_id = random.randint(1, 15)
        quantity = random.randint(1, 5)
        conn.execute(
            "INSERT INTO order_items (order_item_id, order_id, product_id, quantity) VALUES (?, ?, ?, ?)",
            (item_id, order_id, product_id, quantity),
        )
        item_id += 1

    conn.commit()
    conn.close()
    print(f"Created {DB_PATH} with 20 customers, 15 products, 36 orders, 81 order items.")


if __name__ == "__main__":
    generate_db()
