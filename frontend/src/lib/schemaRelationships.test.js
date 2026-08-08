import { describe, it, expect } from "vitest";
import { inferRelationships } from "./schemaRelationships";

describe("schemaRelationships - inferRelationships", () => {
  it("uses real foreign key constraints when present", () => {
    const tables = [
      { name: "users", columns: [{ name: "id" }] },
      {
        name: "posts",
        columns: [{ name: "id" }, { name: "user_id" }],
        foreign_keys: [{ column: "user_id", references_table: "users", references_column: "id" }],
      },
    ];

    const rels = inferRelationships(tables);
    expect(rels).toHaveLength(1);
    expect(rels[0]).toMatchObject({
      from: "posts",
      column: "user_id",
      to: "users",
    });
  });

  it("returns empty array when no relationships exist", () => {
    const tables = [{ name: "table_a", columns: [{ name: "col_a" }] }];
    const rels = inferRelationships(tables);
    expect(rels).toHaveLength(0);
  });
});
