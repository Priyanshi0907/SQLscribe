"""
Database layer for SQLscribe.

Creates and seeds a small SQLite database (RetailDB) with a realistic
retail schema: customers, products, orders, order_items. This gives the
Text-to-SQL assistant real data to query so results are genuine, not
mocked.
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sqlscribe.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    phone       TEXT,
    city        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id     INTEGER PRIMARY KEY,
    product_name   TEXT NOT NULL,
    category       TEXT NOT NULL,
    price          REAL NOT NULL,
    stock_quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date    TEXT NOT NULL,
    status        TEXT NOT NULL,
    total_amount  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id  INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL REFERENCES orders(order_id),
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    quantity       INTEGER NOT NULL,
    unit_price     REAL NOT NULL,
    discount       REAL NOT NULL DEFAULT 0
);
"""

PRODUCT_CATALOG = [
    ("Wireless Headphones", "Electronics", 249.00, 120),
    ("Smart Watch", "Electronics", 189.00, 80),
    ("Gaming Keyboard", "Electronics", 129.00, 60),
    ("Bluetooth Speaker", "Electronics", 99.00, 150),
    ("USB-C Hub", "Electronics", 45.00, 200),
    ("Yoga Mat", "Fitness", 29.00, 300),
    ("Resistance Bands Set", "Fitness", 19.00, 250),
    ("Running Shoes", "Fitness", 89.00, 90),
    ("Stainless Steel Bottle", "Home", 24.00, 220),
    ("Ceramic Coffee Mug", "Home", 14.00, 300),
    ("Desk Lamp", "Home", 34.00, 110),
    ("Backpack 25L", "Accessories", 59.00, 140),
    ("Phone Stand", "Accessories", 12.00, 400),
    ("Laptop Sleeve", "Accessories", 22.00, 180),
    ("Notebook Set", "Stationery", 9.00, 500),
]

FIRST_NAMES = ["Asha", "Rohan", "Priya", "Vikram", "Neha", "Arjun", "Kavya",
               "Rahul", "Sneha", "Aditya", "Meera", "Karan", "Divya", "Sanjay",
               "Pooja", "Amit", "Ritu", "Manish", "Anjali", "Vivek"]
LAST_NAMES = ["Verma", "Mehta", "Nair", "Singh", "Sharma", "Rao", "Patel",
              "Gupta", "Iyer", "Kapoor"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Pune", "Hyderabad",
          "Kolkata", "Ahmedabad", "Jaipur", "Kochi"]
STATUSES = ["pending", "shipped", "delivered", "cancelled"]


def _seed(conn: sqlite3.Connection) -> None:
    random.seed(7)
    cur = conn.cursor()

    customers = []
    for i in range(1, 26):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        created = date(2025, 1, 1) + timedelta(days=random.randint(0, 500))
        customers.append((
            i, f"{fn} {ln}", f"{fn.lower()}.{ln.lower()}{i}@example.com",
            f"+91-9{random.randint(100000000, 999999999)}",
            random.choice(CITIES), created.isoformat(),
        ))
    cur.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?)", customers
    )

    products = []
    for i, (name, cat, price, stock) in enumerate(PRODUCT_CATALOG, start=1):
        products.append((i, name, cat, price, stock))
    cur.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?)", products
    )

    orders = []
    order_items = []
    order_id = 1
    item_id = 1
    for cust in customers:
        for _ in range(random.randint(1, 4)):
            odate = date(2026, 1, 1) + timedelta(days=random.randint(0, 195))
            n_items = random.randint(1, 4)
            chosen = random.sample(PRODUCT_CATALOG, k=min(n_items, len(PRODUCT_CATALOG)))
            order_total = 0.0
            items_for_order = []
            for name, cat, price, stock in chosen:
                pid = next(i for i, p in enumerate(PRODUCT_CATALOG, start=1) if p[0] == name)
                qty = random.randint(1, 5)
                discount = random.choice([0, 0, 0, 5, 10])
                line_total = qty * price * (1 - discount / 100)
                order_total += line_total
                items_for_order.append((item_id, order_id, pid, qty, price, discount))
                item_id += 1
            status = random.choices(STATUSES, weights=[15, 25, 50, 10])[0]
            orders.append((order_id, cust[0], odate.isoformat(), status, round(order_total, 2)))
            order_items.extend(items_for_order)
            order_id += 1

    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", order_items)
    conn.commit()


def init_db(force: bool = False) -> None:
    """Create the database file and seed it if it doesn't already exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = force or not DB_PATH.exists()
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    if is_new:
        cur = conn.execute("SELECT COUNT(*) FROM customers")
        if cur.fetchone()[0] == 0:
            _seed(conn)
    conn.close()


if __name__ == "__main__":
    init_db(force=True)
    print(f"Seeded database at {DB_PATH}")
