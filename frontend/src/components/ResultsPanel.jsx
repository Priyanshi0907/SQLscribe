import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useToast } from "./Toast";

export default function ResultsPanel({ result, loading, error }) {
  const showToast = useToast();
  const [sort, setSort] = useState(null); // { column, direction } | null

  const sortedRows = useMemo(() => {
    if (!result?.rows) return [];
    if (!sort) return result.rows;
    const { column, direction } = sort;
    const factor = direction === "asc" ? 1 : -1;
    return [...result.rows].sort((a, b) => {
      const av = a[column];
      const bv = b[column];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv)) * factor;
    });
  }, [result, sort]);

  // A column reads as numeric if every non-null value in it is a number —
  // used to right-align those columns like a real data grid instead of
  // left-aligning everything uniformly.
  const numericColumns = useMemo(() => {
    if (!result?.rows?.length) return new Set();
    const cols = new Set();
    for (const col of result.columns) {
      const isNumeric = result.rows.every(
        (row) => row[col] === null || row[col] === undefined || typeof row[col] === "number"
      );
      if (isNumeric) cols.add(col);
    }
    return cols;
  }, [result]);

  function toggleSort(column) {
    setSort((prev) => {
      if (!prev || prev.column !== column) return { column, direction: "asc" };
      if (prev.direction === "asc") return { column, direction: "desc" };
      return null;
    });
  }

  function copyCell(value) {
    const text = value === null || value === undefined ? "" : String(value);
    navigator.clipboard.writeText(text);
    showToast("Copied to clipboard.", "success", 1500);
  }

  function exportCsv() {
    if (!result?.rows?.length) return;
    const header = result.columns.join(",");
    const body = result.rows
      .map((row) =>
        result.columns
          .map((col) => {
            const val = row[col];
            const str = val === null || val === undefined ? "" : String(val);
            return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
          })
          .join(",")
      )
      .join("\n");
    const blob = new Blob([`${header}\n${body}`], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sqlscribe_results.csv";
    a.click();
    URL.revokeObjectURL(url);
    showToast("CSV downloaded.", "success", 2000);
  }

  return (
    <div className="relative bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl p-6 h-full flex flex-col shadow-soft dark:shadow-darkSoft">
      <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl bg-gradient-to-r from-primary via-primary/50 to-transparent" />
      <div className="flex items-center justify-between mb-4">
        <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent">
          RESULTS
        </p>
        {result && !result.pending_confirmation && !error && (
          <div className="flex items-center gap-3 text-[11px] text-[#8a8574] dark:text-darkText/50">
            <span className="flex items-center gap-1 text-primary">
              ✓ {result.row_count} rows returned
            </span>
            <span>⏱ {result.elapsed_ms} ms</span>
          </div>
        )}
        {result?.pending_confirmation && !error && (
          <span className="text-[11px] text-accent flex items-center gap-1">⚠ Awaiting confirmation</span>
        )}
      </div>

      {result?.truncated && !error && (
        <div className="mb-3 text-[11px] text-[#8a6a2a] dark:text-[#e0b25a] bg-[#e0b25a]/10 border border-[#e0b25a]/30 rounded-lg px-3 py-2">
          Showing the first {result.row_count} rows. Narrow your question (add a filter or a smaller date range) to see the rest.
        </div>
      )}

      <div className="flex-1 overflow-auto rounded-lg border border-border dark:border-darkBorder">
        {!result && !loading && !error && (
          <div className="h-full min-h-[220px] flex flex-col items-center justify-center text-center px-6 py-8">
            <span className="w-12 h-12 rounded-full bg-primary/10 dark:bg-primary/20 flex items-center justify-center text-xl mb-3">
              🔍
            </span>
            <p className="text-sm font-medium text-[#5A5650] dark:text-darkText/80 mb-3">
              No query executed yet.
            </p>
            <p className="text-xs text-[#a39d8a] dark:text-darkText/40 mb-2">Try asking:</p>
            <ul className="text-xs text-[#8a8574] dark:text-darkText/50 space-y-1.5">
              <li>• Show top 10 customers</li>
              <li>• Monthly revenue trends</li>
              <li>• Which products are low on stock</li>
            </ul>
          </div>
        )}
        {loading && (
          <div className="h-full min-h-[220px] p-4 space-y-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="h-4 rounded skeleton animate-shimmer" style={{ width: `${90 - i * 8}%` }} />
            ))}
          </div>
        )}
        {error && (
          <div className="h-full min-h-[220px] flex items-center justify-center text-sm text-red-700 dark:text-red-300 px-4 text-center">
            {error}
          </div>
        )}
        {result?.pending_confirmation && !error && (
          <div className="h-full min-h-[220px] flex flex-col items-center justify-center text-center px-6 py-8">
            <span className="w-12 h-12 rounded-full bg-accent/10 dark:bg-accent/20 flex items-center justify-center text-xl mb-3">
              ⚠
            </span>
            <p className="text-sm font-medium text-[#5A5650] dark:text-darkText/80 mb-1">
              Waiting for confirmation.
            </p>
            <p className="text-xs text-[#a39d8a] dark:text-darkText/40 max-w-[240px]">
              This query writes to your database. Review it in the dialog and confirm before it runs.
            </p>
          </div>
        )}
        {result && !result.pending_confirmation && !error && (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-bg dark:bg-darkBg border-b border-border dark:border-darkBorder sticky top-0 z-10 shadow-[0_1px_0_rgba(0,0,0,0.02)]">
                {result.columns.map((col) => {
                  const active = sort?.column === col;
                  const isNumeric = numericColumns.has(col);
                  return (
                    <th
                      key={col}
                      onClick={() => toggleSort(col)}
                      className={`font-medium text-[#5A5650] dark:text-darkText/70 px-4 py-2.5 whitespace-nowrap cursor-pointer select-none hover:text-primary transition-colors ${
                        isNumeric ? "text-right" : "text-left"
                      }`}
                      title="Click to sort"
                    >
                      <span className={`flex items-center gap-1 ${isNumeric ? "justify-end" : ""}`}>
                        {col}
                        <span className={`text-[10px] ${active ? "text-primary" : "text-[#c4beb0] dark:text-darkText/25"}`}>
                          {active ? (sort.direction === "asc" ? "▲" : "▼") : "⇅"}
                        </span>
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, i) => (
                <motion.tr
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i, 20) * 0.015 }}
                  className={`group border-b border-border dark:border-darkBorder last:border-0 ${i % 2 === 1 ? "bg-bg/40 dark:bg-darkBg/40" : ""
                    }`}
                >
                  {result.columns.map((col) => (
                    <td
                      key={col}
                      onClick={() => copyCell(row[col])}
                      className={`px-4 py-2.5 text-[#2B2B2B] dark:text-darkText whitespace-nowrap cursor-pointer hover:bg-accent/10 transition-colors ${
                        numericColumns.has(col) ? "text-right font-mono tabular-nums" : "text-left"
                      }`}
                      title="Click to copy"
                    >
                      {formatCell(row[col])}
                    </td>
                  ))}
                </motion.tr>
              ))}
              {sortedRows.length === 0 && (
                <tr>
                  <td
                    colSpan={result.columns.length || 1}
                    className="px-4 py-6 text-center text-[#a39d8a] dark:text-darkText/40"
                  >
                    No rows returned.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <button
        onClick={exportCsv}
        disabled={!result?.rows?.length}
        className="mt-4 w-full border border-border dark:border-darkBorder rounded-lg py-2.5 text-sm font-medium text-accent hover:bg-accent/5 disabled:opacity-40 disabled:hover:bg-transparent transition-colors flex items-center justify-center gap-2"
      >
        ⬇ Export CSV
      </button>
    </div>
  );
}

function formatCell(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value : value.toFixed(2);
  }
  return String(value);
}