import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

export default function DatabaseSelector({ selected, onSwitchDatabase }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs bg-bg dark:bg-darkBg border border-border dark:border-darkBorder rounded-full px-3 py-1.5 text-[#3a382f] dark:text-darkText/80 font-medium hover:bg-border/30 dark:hover:bg-darkBorder/30 transition-colors"
      >
        🗄 {selected}
        <span className={`text-[9px] text-[#a39d8a] transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-60 bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-xl shadow-lg overflow-hidden z-20"
          >
            <p className="text-[10px] font-bold tracking-wide text-sqlText dark:text-accent px-3 pt-3 pb-1">
              CURRENT DATABASE
            </p>
            <div className="px-3 py-2 flex items-center gap-1.5 text-sm text-[#2B2B2B] dark:text-darkText">
              <span className="text-primary">✓</span>
              {selected}
            </div>
            <div className="border-t border-border dark:border-darkBorder">
              <button
                onClick={() => {
                  setOpen(false);
                  onSwitchDatabase();
                }}
                className="w-full text-left px-3 py-2.5 text-sm text-accent hover:bg-bg dark:hover:bg-darkBg transition-colors"
              >
                ↺ Switch database…
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}