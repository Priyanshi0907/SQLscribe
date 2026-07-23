const KEYWORDS = [
  "SELECT", "FROM", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
  "ON", "GROUP BY", "ORDER BY", "LIMIT", "AS", "AND", "OR", "NOT", "IN",
  "SUM", "COUNT", "AVG", "MIN", "MAX", "DESC", "ASC", "DISTINCT",
  "HAVING", "BETWEEN", "LIKE", "IS", "NULL", "CASE", "WHEN", "THEN", "END",
];

// Longer phrases first so "GROUP BY" matches before a lone "BY" would.
const sorted = [...KEYWORDS].sort((a, b) => b.length - a.length);
const pattern = new RegExp(`\\b(${sorted.join("|")})\\b`, "gi");

/**
 * Splits a SQL string into an array of { text, isKeyword } tokens
 * for rendering with keyword coloring in the terminal panel.
 */
export function tokenizeSql(sql) {
  const tokens = [];
  let lastIndex = 0;
  let match;
  pattern.lastIndex = 0;

  while ((match = pattern.exec(sql)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ text: sql.slice(lastIndex, match.index), isKeyword: false });
    }
    tokens.push({ text: match[0], isKeyword: true });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < sql.length) {
    tokens.push({ text: sql.slice(lastIndex), isKeyword: false });
  }
  return tokens;
}
