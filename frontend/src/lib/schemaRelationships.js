/**
 * Infers foreign-key relationships by matching a column name against
 * another table's first column (assumed primary key by convention —
 * true for any table built with an "<id_column> INTEGER PRIMARY KEY"
 * first column, which is how every table in this schema is defined).
 *
 * This means relationships are derived from the live schema, not
 * hardcoded — add a table with a matching *_id column and a relationship
 * is picked up automatically, no changes needed here.
 */
export function inferRelationships(tables) {
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
