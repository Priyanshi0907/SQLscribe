import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { fetchHistory } from "../lib/api";

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export default function HistoryView({ onSelect, onDelete, onToggleFavorite, onClearAll }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  useEffect(() => {
    fetchHistory(50)
      .then((data) => setItems(data.history))
      .catch((err) => setError(err.message));
  }, []);

  function handleDelete(id) {
    setItems((prev) => prev.filter((item) => item.id !== id));
    onDelete(id);
  }

  function handleToggleFavorite(id, next) {
    setItems((prev) => prev.map((item) => (item.id === id ? { ...item, is_favorite: next } : item)));
    onToggleFavorite?.(id, next);
  }

  function handleClearAll() {
    setItems([]);
    setConfirmingClear(false);
    onClearAll();
  }

  const visibleItems = favoritesOnly ? items?.filter((i) => i.is_favorite) : items;

  return (
    <div className="relative bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl p-6 shadow-soft dark:shadow-darkSoft">
      <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl bg-gradient-to-r from-sqlText via-sqlText/40 to-transparent dark:from-accent dark:via-accent/40" />
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-mono text-[34px] font-black text-[#2B2B2B] dark:text-darkText tracking-tight">
            Recent queries
          </h1>
          <p className="text-sm text-[#7a7566] dark:text-darkText/60 mt-1 mb-6">
            Every question you've asked. Click one to view its results — nothing is re-run.
          </p>
        </div>

        {items && items.length > 0 && (
          <div className="shrink-0 pt-1">
            {confirmingClear ? (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-[#7a7566] dark:text-darkText/60">Clear all history?</span>
                <button
                  onClick={handleClearAll}
                  className="text-red-600 dark:text-red-400 font-medium hover:underline"
                >
                  Yes, clear
                </button>
                <button
                  onClick={() => setConfirmingClear(false)}
                  className="text-[#a39d8a] dark:text-darkText/40 hover:underline"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmingClear(true)}
                className="text-xs text-[#a39d8a] dark:text-darkText/40 hover:text-red-600 dark:hover:text-red-400 font-medium transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
        )}
      </div>

      {items && items.length > 0 && (
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => setFavoritesOnly(false)}
            className={`text-xs font-medium rounded-full px-3 py-1.5 border transition-colors ${
              !favoritesOnly
                ? "bg-primary text-white border-primary"
                : "text-[#7a7566] dark:text-darkText/60 border-border dark:border-darkBorder hover:border-primary/40"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFavoritesOnly(true)}
            className={`text-xs font-medium rounded-full px-3 py-1.5 border transition-colors flex items-center gap-1 ${
              favoritesOnly
                ? "bg-primary text-white border-primary"
                : "text-[#7a7566] dark:text-darkText/60 border-border dark:border-darkBorder hover:border-primary/40"
            }`}
          >
            ★ Pinned
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-300">Couldn't load history: {error}</p>}
      {!items && !error && <p className="text-sm text-[#a39d8a] dark:text-darkText/40">Loading…</p>}
      {items?.length === 0 && (
        <p className="text-sm text-[#a39d8a] dark:text-darkText/40 py-6 text-center">No queries yet — ask something on the New Query tab.</p>
      )}
      {items?.length > 0 && visibleItems.length === 0 && (
        <p className="text-sm text-[#a39d8a] dark:text-darkText/40 py-6 text-center">No pinned queries yet — click the star on one to pin it.</p>
      )}

      <ul className="divide-y divide-border dark:divide-darkBorder">
        <AnimatePresence initial={false}>
          {visibleItems?.map((item) => (
            <motion.li
              key={item.id}
              layout
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, height: 0 }}
              className="group flex items-start gap-1 -mx-2 px-2 rounded-lg hover:bg-bg/50 dark:hover:bg-darkBg/50 transition-colors"
            >
              <button
                onClick={() => handleToggleFavorite(item.id, !item.is_favorite)}
                title={item.is_favorite ? "Unpin" : "Pin this query"}
                className={`shrink-0 mt-3 w-6 h-6 flex items-center justify-center transition-colors ${
                  item.is_favorite ? "text-accent" : "text-[#d8d2c2] dark:text-darkText/20 hover:text-accent"
                }`}
              >
                {item.is_favorite ? "★" : "☆"}
              </button>
              <button
                onClick={() => onSelect(item)}
                className="flex-1 text-left py-3 min-w-0"
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2.5 text-sm text-[#2B2B2B] dark:text-darkText min-w-0">
                    <span className="truncate">{item.question}</span>
                  </span>
                  <span className="flex items-center gap-4 text-xs text-[#a39d8a] dark:text-darkText/40 shrink-0 ml-4">
                    <span>{timeAgo(item.created_at)}</span>
                    <span>{item.row_count} rows</span>
                    <span>{item.elapsed_ms} ms</span>
                  </span>
                </div>
                <p className="mt-1.5 ml-0 font-mono text-[11px] text-[#a39d8a] dark:text-darkText/40 truncate">
                  {item.sql_text}
                </p>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(item.id);
                }}
                title="Delete from history"
                className="shrink-0 mt-3 w-7 h-7 rounded-md flex items-center justify-center text-[#c4beb0] dark:text-darkText/25 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 opacity-0 group-hover:opacity-100 transition-opacity"
              >
                🗑
              </button>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}