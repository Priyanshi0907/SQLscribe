import { createContext, useCallback, useContext, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

const ToastContext = createContext(null);

const VARIANTS = {
  success: { icon: "✓", accent: "border-l-primary", text: "text-primary" },
  error: { icon: "✕", accent: "border-l-red-500", text: "text-red-700" },
  info: { icon: "ℹ", accent: "border-l-accent", text: "text-accent" },
};

let nextId = 1;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (message, variant = "info", duration = 4000) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, message, variant }]);
      if (duration) setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 w-[320px] max-w-[calc(100vw-2.5rem)]">
        <AnimatePresence>
          {toasts.map((t) => {
            const cfg = VARIANTS[t.variant] || VARIANTS.info;
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, y: 12, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 40, transition: { duration: 0.15 } }}
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
                className={`bg-card dark:bg-darkCard border border-border dark:border-darkBorder ${cfg.accent} border-l-[3px] rounded-xl shadow-lg px-4 py-3 flex items-start gap-2.5`}
              >
                <span className={`${cfg.text} text-sm font-bold shrink-0 mt-0.5`}>{cfg.icon}</span>
                <p className="text-sm text-[#2B2B2B] dark:text-darkText flex-1 leading-snug">
                  {t.message}
                </p>
                <button
                  onClick={() => dismiss(t.id)}
                  className="text-[#a39d8a] hover:text-[#5A5650] dark:hover:text-darkText text-xs shrink-0"
                  aria-label="Dismiss notification"
                >
                  ✕
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

/**
 * useToast() returns showToast(message, variant, durationMs).
 * variant: "success" | "error" | "info" (default "info").
 * Pass duration: 0 to keep the toast until manually dismissed.
 */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fail soft rather than crash the app if a component renders outside
    // the provider during development.
    return () => {};
  }
  return ctx;
}