/**
 * Detects badges (Primary Key and References) for a column within a table schema.
 */
export function getColumnBadges(table, column, allTables = []) {
  const badges = [];

  // 1. Primary Key Detection
  const tableNameLower = (table.name || "").toLowerCase();
  const colNameLower = (column.name || "").toLowerCase();
  const singularTable = tableNameLower.endsWith("s")
    ? tableNameLower.slice(0, -1)
    : tableNameLower;

  const isPk =
    column.pk === true ||
    column.is_pk === true ||
    column.primary_key === true ||
    colNameLower === "id" ||
    colNameLower === `${tableNameLower}_id` ||
    colNameLower === `${singularTable}_id`;

  if (isPk) {
    badges.push({
      type: "primary_key",
      label: "Primary key",
    });
  }

  // 2. References Detection
  let refTable = null;
  let refCol = null;

  // Check explicit foreign keys from backend metadata first
  const explicitFk = (table.foreign_keys || []).find((fk) => fk.column === column.name);
  if (explicitFk) {
    refTable = explicitFk.references_table;
    refCol = explicitFk.references_column || explicitFk.column;
  } else if (!isPk && colNameLower.endsWith("_id")) {
    // Fallback heuristic for foreign keys: column ends with _id
    const baseName = colNameLower.replace(/_id$/, "");
    const matchingTable = allTables.find((t) => {
      if (t.name === table.name) return false;
      const tLower = t.name.toLowerCase();
      return (
        tLower === baseName ||
        tLower === `${baseName}s` ||
        tLower === `${baseName}es` ||
        tLower === baseName.replace(/y$/, "ies")
      );
    });

    if (matchingTable) {
      refTable = matchingTable.name;
      // find PK column in matching table, or use matching column name / id
      const targetPk =
        matchingTable.columns.find(
          (c) => c.pk || c.name.toLowerCase() === colNameLower || c.name.toLowerCase() === "id"
        )?.name || column.name;
      refCol = targetPk;
    }
  }

  // CRITICAL REQUIREMENT:
  // "deleting the referenced table must remove this referencing icon automatically"
  // Check if referenced table STILL EXISTS in current active schema (`allTables`).
  if (refTable) {
    const referencedTableExists = allTables.some(
      (t) => t.name.toLowerCase() === refTable.toLowerCase()
    );
    if (referencedTableExists) {
      // Find actual casing of target table name
      const actualTable = allTables.find((t) => t.name.toLowerCase() === refTable.toLowerCase());
      const displayTable = actualTable ? actualTable.name : refTable;

      badges.push({
        type: "reference",
        label: `References ${displayTable}.${refCol}`,
        targetTable: displayTable,
        targetColumn: refCol,
      });
    }
  }

  return badges;
}
