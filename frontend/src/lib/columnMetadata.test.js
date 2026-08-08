import { describe, it, expect } from "vitest";
import { getColumnBadges } from "./columnMetadata";

describe("columnMetadata - getColumnBadges", () => {
  const allTables = [
    { name: "customers", columns: [{ name: "customer_id", pk: true }] },
    {
      name: "orders",
      columns: [{ name: "order_id", pk: true }, { name: "customer_id" }],
      foreign_keys: [
        { column: "customer_id", references_table: "customers", references_column: "customer_id" },
      ],
    },
  ];

  it("identifies primary key badge from column.pk flag", () => {
    const table = allTables[0];
    const col = table.columns[0];
    const badges = getColumnBadges(table, col, allTables);

    expect(badges).toHaveLength(1);
    expect(badges[0]).toEqual({ type: "primary_key", label: "Primary key" });
  });

  it("identifies foreign key reference badge when referenced table exists", () => {
    const table = allTables[1];
    const col = table.columns[1]; // customer_id
    const badges = getColumnBadges(table, col, allTables);

    expect(badges).toHaveLength(1);
    expect(badges[0]).toMatchObject({
      type: "reference",
      label: "References customers.customer_id",
      targetTable: "customers",
      targetColumn: "customer_id",
    });
  });

  it("suppresses reference badge if target referenced table is dropped from active schema", () => {
    const table = allTables[1];
    const col = table.columns[1];
    const activeTablesOnly = [allTables[1]]; // customers table dropped

    const badges = getColumnBadges(table, col, activeTablesOnly);
    expect(badges).toHaveLength(0);
  });
});
