"""
schema_context.py
-----------------
Single source of truth for the database schema context.
Matches Section 3 of the Project Design Report.
"""

SCHEMA_CONTEXT = """
DATABASE SCHEMA:

Table 1: customers
Columns:
  - customer_id (INTEGER, PRIMARY KEY)
  - name (TEXT)
  - email (TEXT)
  - city (TEXT)

Table 2: products
Columns:
  - product_id (INTEGER, PRIMARY KEY)
  - product_name (TEXT)
  - category (TEXT)
  - price (DECIMAL)

Table 3: orders
Columns:
  - order_id (INTEGER, PRIMARY KEY)
  - customer_id (INTEGER, FOREIGN KEY -> customers.customer_id)
  - order_date (DATE, format: YYYY-MM-DD)
  - status (TEXT, values: 'shipped', 'delivered', 'pending', 'cancelled')

Table 4: order_items
Columns:
  - order_item_id (INTEGER, PRIMARY KEY)
  - order_id (INTEGER, FOREIGN KEY -> orders.order_id)
  - product_id (INTEGER, FOREIGN KEY -> products.product_id)
  - quantity (INTEGER)

RELATIONSHIPS:
- customers.customer_id = orders.customer_id (1:N)
- orders.order_id = order_items.order_id (1:N)
- products.product_id = order_items.product_id (1:N)
"""
