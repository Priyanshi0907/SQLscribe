"""
Tests for app/sql_guard.py — the core safety layer. These are the checks
that decide whether generated SQL is even allowed to reach a database, so
they're the highest-value tests in this project to keep passing.
"""

import pytest

from app.sql_guard import SQLValidationError, validate_sql

TABLES = {"customers", "orders", "order_items", "products"}


class TestReadOnlyDetection:
    def test_select_is_read_only(self):
        _, is_read_only = validate_sql("SELECT * FROM customers", TABLES)
        assert is_read_only is True

    def test_insert_is_not_read_only(self):
        _, is_read_only = validate_sql(
            "INSERT INTO customers (name) VALUES ('Priya')", TABLES
        )
        assert is_read_only is False

    def test_update_with_where_is_not_read_only(self):
        _, is_read_only = validate_sql(
            "UPDATE customers SET name = 'Priya' WHERE customer_id = 1", TABLES
        )
        assert is_read_only is False


class TestTableValidation:
    def test_known_table_passes(self):
        formatted, _ = validate_sql("SELECT * FROM customers", TABLES)
        assert "customers" in formatted.lower()

    def test_unknown_table_is_rejected(self):
        with pytest.raises(SQLValidationError, match="unknown table"):
            validate_sql("SELECT * FROM secret_admin_table", TABLES)

    def test_join_pulls_in_all_referenced_tables(self):
        sql = (
            "SELECT o.order_id, c.name FROM orders o "
            "JOIN customers c ON o.customer_id = c.customer_id"
        )
        formatted, is_read_only = validate_sql(sql, TABLES)
        assert is_read_only is True
        assert "join" in formatted.lower()

    def test_join_against_unknown_table_is_rejected(self):
        sql = (
            "SELECT * FROM orders o "
            "JOIN not_a_real_table x ON o.order_id = x.order_id"
        )
        with pytest.raises(SQLValidationError, match="unknown table"):
            validate_sql(sql, TABLES)

    def test_cte_names_are_not_treated_as_unknown_tables(self):
        sql = (
            "WITH big_orders AS (SELECT * FROM orders WHERE total_amount > 100) "
            "SELECT * FROM big_orders"
        )
        formatted, _ = validate_sql(sql, TABLES)
        assert "big_orders" in formatted.lower()

    def test_create_table_target_is_allowed_even_though_it_doesnt_exist_yet(self):
        formatted, is_read_only = validate_sql(
            "CREATE TABLE returns (id INTEGER PRIMARY KEY)", TABLES
        )
        assert is_read_only is False
        assert "returns" in formatted.lower()


class TestInjectionAndMultiStatementBlocking:
    def test_multiple_statements_are_rejected(self):
        with pytest.raises(SQLValidationError, match="Multiple statements"):
            validate_sql("SELECT * FROM customers; DROP TABLE customers", TABLES)

    def test_line_comment_is_rejected(self):
        with pytest.raises(SQLValidationError, match="comments"):
            validate_sql("SELECT * FROM customers -- sneaky comment", TABLES)

    def test_block_comment_is_rejected(self):
        with pytest.raises(SQLValidationError, match="comments"):
            validate_sql("SELECT * FROM customers /* sneaky */", TABLES)

    def test_empty_sql_is_rejected(self):
        with pytest.raises(SQLValidationError, match="empty"):
            validate_sql("   ", TABLES)

    def test_unparseable_sql_is_rejected(self):
        with pytest.raises(SQLValidationError, match="parse"):
            validate_sql("SELEKT * FRUM nowhere ???", TABLES)


class TestWhereClauseRequirement:
    """The fix for the biggest gap in this project: UPDATE/DELETE must
    be scoped to specific rows, not just flagged as risky and left to
    the user to double-check."""

    def test_delete_with_no_where_is_blocked(self):
        with pytest.raises(SQLValidationError, match="WHERE clause"):
            validate_sql("DELETE FROM customers", TABLES)

    def test_update_with_no_where_is_blocked(self):
        with pytest.raises(SQLValidationError, match="WHERE clause"):
            validate_sql("UPDATE orders SET status = 'shipped'", TABLES)

    def test_delete_with_trivially_true_where_is_blocked(self):
        with pytest.raises(SQLValidationError, match="doesn't actually filter"):
            validate_sql("DELETE FROM customers WHERE 1=1", TABLES)

    def test_delete_with_real_where_passes(self):
        formatted, is_read_only = validate_sql(
            "DELETE FROM customers WHERE customer_id = 5", TABLES
        )
        assert is_read_only is False
        assert "customer_id" in formatted.lower()

    def test_update_with_real_where_passes(self):
        formatted, is_read_only = validate_sql(
            "UPDATE orders SET status = 'shipped' WHERE order_id = 10", TABLES
        )
        assert is_read_only is False

    def test_select_never_needs_a_where_clause(self):
        # Sanity check: the requirement is specific to writes, not a
        # blanket "every query needs a WHERE" rule.
        formatted, is_read_only = validate_sql("SELECT * FROM customers", TABLES)
        assert is_read_only is True

    def test_multitable_update_via_join_still_requires_where(self):
        sql = (
            "UPDATE orders o JOIN customers c ON o.customer_id = c.customer_id "
            "SET o.status = 'vip'"
        )
        with pytest.raises(SQLValidationError, match="WHERE clause"):
            validate_sql(sql, TABLES, dialect="mysql")

    def test_multitable_update_via_join_with_where_passes(self):
        sql = (
            "UPDATE orders o JOIN customers c ON o.customer_id = c.customer_id "
            "SET o.status = 'vip' WHERE c.city = 'Delhi'"
        )
        formatted, is_read_only = validate_sql(sql, TABLES, dialect="mysql")
        assert is_read_only is False

    def test_delete_using_with_where_passes(self):
        sql = (
            "DELETE FROM orders o USING customers c "
            "WHERE o.customer_id = c.customer_id AND c.city = 'Delhi'"
        )
        formatted, is_read_only = validate_sql(sql, TABLES, dialect="postgres")
        assert is_read_only is False

    def test_delete_scoped_by_subquery_passes(self):
        sql = (
            "DELETE FROM order_items WHERE order_id IN "
            "(SELECT order_id FROM orders WHERE customer_id = 3)"
        )
        formatted, is_read_only = validate_sql(sql, TABLES)
        assert is_read_only is False


class TestDialectAwareness:
    def test_postgres_dialect_formats_without_error(self):
        formatted, _ = validate_sql(
            'SELECT * FROM "customers" LIMIT 10', TABLES, dialect="postgres"
        )
        assert "customers" in formatted.lower()

    def test_mysql_dialect_formats_without_error(self):
        formatted, _ = validate_sql(
            "SELECT * FROM `customers` LIMIT 10", TABLES, dialect="mysql"
        )
        assert "customers" in formatted.lower()
