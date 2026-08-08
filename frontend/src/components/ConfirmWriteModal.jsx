import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { tokenizeSql } from "../lib/highlightSql";

// Statements that destroy data/structure outright get the strongest
// framing. INSERT/UPDATE/CREATE change data but don't erase anything by
// themselves, so they get a milder warning tone.
const HIGH_RISK = new Set(["DELETE", "DROP", "TRUNCATE", "ALTER"]);

function statementType(sql) {
  const match = sql.trim().match(/^([A-Za-z]+)/);
  return match ? match[1].toUpperCase() : "WRITE";
}

export default function ConfirmWriteModal({ open, sql, dialect, onConfirm, onCancel }) {
  const [confirming, setConfirming] = useState(false);
  const cancelButtonRef = useRef(null);

  // Focus the Cancel button (not the destructive Confirm one) as soon as
  // the modal opens, so keyboard/screen-reader users land somewhere safe
  // by default instead of having to tab in from wherever focus happened
  // to be on the page underneath.
  useEffect(() => {
    if (open) {
      cancelButtonRef.current?.focus();
    }
  }, [open]);

  // Escape cancels — same as clicking outside or the Cancel button —
  // but never while a confirm is actually in flight, so a slow write
  // can't be silently abandoned mid-request by an accidental keypress.
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape" && !confirming) {
        onCancel();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, confirming, onCancel]);

  if (!open) return null;

  const type = statementType(sql);
  const highRisk = HIGH_RISK.has(type);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await onConfirm();
    } finally {
      setConfirming(false);
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        key="backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        aria-describedby="confirm-modal-desc"
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
        onClick={() => !confirming && onCancel()}
      >
        <motion.div
          key="modal"
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={{ duration: 0.18 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-lg bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl shadow-softHover dark:shadow-darkSoftHover overflow-hidden"
        >
          <div className="px-6 pt-6 pb-4">
            <div className="flex items-start gap-3">
              <span
                className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center text-base ${
                  highRisk
                    ? "bg-[#e0605a]/15 text-[#c9453e]"
                    : "bg-accent/15 text-accent"
                }`}
              >
                ⚠
              </span>
              <div>
                <h2 id="confirm-modal-title" className="font-mono text-lg font-black text-[#2B2B2B] dark:text-darkText">
                  Confirm {type} query
                </h2>
                <p id="confirm-modal-desc" className="text-sm text-[#7a7566] dark:text-darkText/60 mt-1">
                  {highRisk
                    ? "This statement changes or removes existing data and cannot be undone. Review it carefully before running it."
                    : "This statement will write to your database. Review it before running it."}
                </p>
              </div>
            </div>
          </div>

          <div className="mx-6 rounded-xl overflow-hidden border border-[#1c1c1c]/20">
            <div className="bg-terminal px-4 py-2.5 flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#e0605a]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#e0b25a]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#63b56b]" />
              <span className="ml-auto text-[11px] text-[#9c9689]">{dialect || "SQL"}</span>
            </div>
            <div className="bg-terminal px-4 py-4 font-mono text-[13px] leading-6 max-h-64 overflow-auto">
              <pre className="whitespace-pre-wrap break-words">
                {tokenizeSql(sql).map((tok, i) =>
                  tok.isKeyword ? (
                    <span key={i} className="text-accent font-semibold">
                      {tok.text}
                    </span>
                  ) : (
                    <span key={i} className="text-[#e4e0d6]">
                      {tok.text}
                    </span>
                  )
                )}
              </pre>
            </div>
          </div>

          <div className="px-6 py-5 flex items-center justify-end gap-3">
            <button
              ref={cancelButtonRef}
              type="button"
              onClick={onCancel}
              disabled={confirming}
              className="px-4 py-2 text-sm font-semibold text-[#7a7566] dark:text-darkText/70 hover:text-[#2B2B2B] dark:hover:text-darkText transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <motion.button
              type="button"
              onClick={handleConfirm}
              disabled={confirming}
              whileTap={{ scale: 0.96 }}
              className={`px-4 py-2 rounded-lg text-sm font-semibold text-white flex items-center gap-2 transition-opacity disabled:opacity-60 ${
                highRisk ? "bg-[#c9453e] hover:opacity-90" : "bg-primary hover:opacity-90"
              }`}
            >
              {confirming && (
                <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              )}
              {confirming ? "Running…" : `Run ${type}`}
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
