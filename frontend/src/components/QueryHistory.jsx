import { AnimatePresence, motion } from "framer-motion";

function timeAgo(isoString) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export default function QueryHistory({ items, onSelect, onDelete, onToggleFavorite, onViewAll }) {
  return (
    <div className="relative bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl p-6 shadow-soft dark:shadow-darkSoft">
      <div className="absolute top-0 left-0 right-0 h-[3px] rounded-t-2xl bg-gradient-to-r from-sqlText via-sqlText/40 to-transparent dark:from-accent dark:via-accent/40" />
      <div className="flex items-center justify-between mb-3">
        <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent">
          RECENT QUERIES
        </p>
        <button
          onClick={onViewAll}
          className="text-xs text-accent font-medium flex items-center gap-1 hover:underline"
        >
          View all →
        </button>
      </div>

      {items.length === 0 && (
        <p className="text-sm text-[#a39d8a] dark:text-darkText/40 py-4 text-center">
          Your recent queries will show up here.
        </p>
      )}

      <ul className="divide-y divide-border dark:divide-darkBorder">
        <AnimatePresence initial={false}>
          {items.map((item) => (
            <motion.li
              key={item.id}
              layout
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, height: 0 }}
              className="group flex items-center gap-1 -mx-2 px-2 rounded-lg hover:bg-bg/50 dark:hover:bg-darkBg/50 transition-colors"
            >
              <button
                onClick={() =>
                  onToggleFavorite ? onToggleFavorite(item.id, !item.is_favorite) : undefined
                }
                title={item.is_favorite ? "Unpin" : "Pin this query"}
                className={`shrink-0 w-6 h-6 flex items-center justify-center transition-colors ${
                  item.is_favorite ? "text-accent" : "text-[#d8d2c2] dark:text-darkText/20 hover:text-accent"
                }`}
              >
                {item.is_favorite ? "★" : "☆"}
              </button>
              <button
                onClick={() => onSelect(item)}
                className="flex-1 flex items-center justify-between py-3 text-left min-w-0"
              >
                <span className="flex items-center gap-2.5 text-sm text-[#2B2B2B] dark:text-darkText min-w-0">
                  <span className="truncate">{item.question}</span>
                </span>
                <span className="flex items-center gap-4 text-xs text-[#a39d8a] dark:text-darkText/40 shrink-0 ml-4">
                  <span>{timeAgo(item.created_at)}</span>
                  <span>{item.elapsed_ms} ms</span>
                </span>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(item.id);
                }}
                title="Delete from history"
                className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-[#c4beb0] dark:text-darkText/25 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 opacity-0 group-hover:opacity-100 transition-opacity"
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