/**
 * Derives foreign-key relationships to draw in the ER diagram.
 *
 * Prefers real FK constraints read from the connected database's own
 * catalog/pragma (table.foreign_keys, populated by the backend's
 * sources.get_schema_metadata — see backend/app/sources.py) over the
 * naming-convention guess this used to rely on exclusively. Real
 * constraints are ground truth: a table can be named anything and still
 * get its relationships drawn correctly, whereas the naming heuristic
 * only works when every table happens to follow an "<id_column> INTEGER
 * PRIMARY KEY" convention.
 *
 * Falls back to the heuristic per-table, not globally: if the connected
 * database declares no FK constraints at all (e.g. a SQLite file built
 * without REFERENCES clauses, or a schema created without enforcing
 * them), relationships are still inferred from naming so the diagram
 * isn't left empty. Tables that DO have real constraints never fall
 * back — a declared, real relationship always wins over a guess.
 */
export function inferRelationships(tables) {
  const hasAnyRealForeignKeys = tables.some((t) => (t.foreign_keys || []).length > 0);

  if (hasAnyRealForeignKeys) {
    const relationships = [];
    const seen = new Set();
    tables.forEach((t) => {
      (t.foreign_keys || []).forEach((fk) => {
        // Only draw an edge to a table that's actually part of this
        // schema view (guards against a dangling/renamed reference).
        if (!tables.some((other) => other.name === fk.references_table)) return;
        const key = `${t.name}::${fk.column}::${fk.references_table}`;
        if (seen.has(key)) return;
        seen.add(key);
        relationships.push({ from: t.name, to: fk.references_table, column: fk.column });
      });
    });
    return relationships;
  }

  return _inferRelationshipsByNamingConvention(tables);
}

function _inferRelationshipsByNamingConvention(tables) {
  const pkByTable = {};
  tables.forEach((t) => {
    if (t.columns.length) pkByTable[t.name] = t.columns[0].name;
  });

  const relationships = [];
  tables.forEach((t) => {
    t.columns.forEach((col, idx) => {
      if (idx === 0) return; // this is the table's own primary key, not a reference
      const match = Object.entries(pkByTable).find(
        ([tableName, pkCol]) => tableName !== t.name && pkCol === col.name
      );
      if (match) {
        relationships.push({ from: t.name, to: match[0], column: col.name });
      }
    });
  });
  return relationships;
}
