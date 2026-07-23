import { useState } from "react";
import { motion } from "framer-motion";
import { tokenizeSql } from "../lib/highlightSql";
import ConnectionStatus from "./ConnectionStatus";
import DatabaseSelector from "./DatabaseSelector";

const EXAMPLE_QUESTIONS = [
  "Top 5 customers by total spend",
  "Monthly revenue trends",
  "Which products are low on stock",
];

export default function QueryPanel({ onRun, loading, result, error, dbName, onSwitchDatabase, initialQuestion }) {
  const [question, setQuestion] = useState(
    initialQuestion ?? ""
  );
  const [copied, setCopied] = useState(false);

  function handleSubmit(e) {
    e?.preventDefault();
    if (!question.trim() || loading) return;
    onRun(question.trim());
  }

  function handleKeyDown(e) {
    // Cmd/Ctrl+Enter runs the query without leaving the textarea.
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleCopy() {
    if (!result?.sql) return;
    navigator.clipboard.writeText(result.sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const showExamples = !loading && !error && !result?.sql && !question;

  return (
    <div className="relative bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl p-6 shadow-soft dark:shadow-darkSoft">
      <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl bg-gradient-to-r from-accent via-accent/50 to-transparent" />
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="font-mono text-[34px] font-black text-[#2B2B2B] dark:text-darkText tracking-tight">
            Ask your database anything
          </h1>
          <p className="text-sm text-[#7a7566] dark:text-darkText/60 mt-1">
            Convert natural language to SQL and get instant insights.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <ConnectionStatus />
          <DatabaseSelector selected={dbName || "Database"} onSwitchDatabase={onSwitchDatabase} />
        </div>
      </div>

      <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent mb-2">
        YOUR QUESTION
      </p>
      <form onSubmit={handleSubmit} className="mb-2">
        <div className="border border-border dark:border-darkBorder rounded-xl bg-white/60 dark:bg-darkBg/60 p-1 flex items-end gap-2 focus-within:border-primary/50 transition-colors">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="e.g. Show me the top 5 customers by total orders"
            className="flex-1 resize-none bg-transparent px-3 py-2.5 text-sm font-mono text-[#2B2B2B] dark:text-darkText focus:outline-none placeholder:text-[#a39d8a] dark:placeholder:text-darkText/30"
          />
          <motion.button
            type="submit"
            disabled={loading}
            whileTap={{ scale: 0.92 }}
            className="m-1.5 shrink-0 w-9 h-9 rounded-lg bg-primary text-white flex items-center justify-center hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
            aria-label="Run query"
          >
            {loading ? (
              <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              "➤"
            )}
          </motion.button>
        </div>
      </form>
      <p className="text-[11px] text-[#a39d8a] dark:text-darkText/40 mb-4">
        Press <kbd className="px-1 py-0.5 rounded border border-border dark:border-darkBorder bg-bg dark:bg-darkBg font-mono">Ctrl</kbd>
        {" + "}
        <kbd className="px-1 py-0.5 rounded border border-border dark:border-darkBorder bg-bg dark:bg-darkBg font-mono">Enter</kbd> to run.
      </p>

      {showExamples && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-wrap gap-2 mb-6"
        >
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              className="text-xs text-[#7a7566] dark:text-darkText/60 bg-bg dark:bg-darkBg border border-border dark:border-darkBorder rounded-full px-3 py-1.5 hover:border-primary/40 hover:text-primary transition-colors"
            >
              {q}
            </button>
          ))}
        </motion.div>
      )}

      <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent mb-2">
        GENERATED SQL
      </p>
      <div className="rounded-xl overflow-hidden border border-[#1c1c1c]/20 shadow-soft dark:shadow-darkSoft">
        <div className="bg-terminal px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#e0605a]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#e0b25a]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#63b56b]" />
          </div>
          {result?.sql && (
            <button
              onClick={handleCopy}
              className="text-[11px] text-[#c9c3b4] hover:text-white flex items-center gap-1.5 border border-white/15 rounded-md px-2 py-1 transition-colors"
            >
              {copied ? "Copied" : "⧉ Copy SQL"}
            </button>
          )}
        </div>
        <div className="bg-terminal px-4 py-4 min-h-[160px] font-mono text-[13px] leading-6">
          {error && (
            <p className="text-[#e0847a]">{error}</p>
          )}
          {!error && !result?.sql && !loading && (
            <p className="text-[#6b6a64]">
              Your generated SQL will appear here once you ask a question.
            </p>
          )}
          {!error && loading && (
            <p className="text-[#8a8578] flex items-center gap-2.5">
              <span className="w-3.5 h-3.5 border-2 border-[#8a8578]/30 border-t-[#8a8578] rounded-full animate-spin shrink-0" />
              Generating SQL…
            </p>
          )}
          {!error && result?.sql && (
            <SqlCode sql={result.sql} />
          )}
        </div>
        {result?.sql && !error && (
          <div className="bg-terminal border-t border-white/10 px-4 py-2.5 flex items-center justify-between text-[11px]">
            <span className="text-[#7fbf87] flex items-center gap-1.5">
              ✓ SQL validated successfully
            </span>
            <span className="flex items-center gap-3 text-[#9c9689]">
              <span>{result.dialect || "SQLite"}</span>
              <span className="flex items-center gap-1">🔒 {result.read_only ? "Read-only" : "Read-write"}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function SqlCode({ sql }) {
  const lines = sql.split("\n");
  return (
    <pre className="whitespace-pre-wrap break-words">
      {lines.map((line, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.03, duration: 0.2 }}
          className="flex"
        >
          <span className="text-[#5c5b56] select-none w-6 text-right mr-4 shrink-0">
            {i + 1}
          </span>
          <span>
            {tokenizeSql(line).map((tok, j) =>
              tok.isKeyword ? (
                <span key={j} className="text-accent font-semibold">
                  {tok.text}
                </span>
              ) : (
                <span key={j} className="text-[#e4e0d6]">
                  {tok.text}
                </span>
              )
            )}
          </span>
        </motion.div>
      ))}
    </pre>
  );
}