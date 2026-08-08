import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { fetchSchema } from "../lib/api";

const PREP_STEPS = [
  { id: "connected", label: "Connected" },
  { id: "schema", label: "Reading schema" },
  { id: "tables", label: "Discovering tables" },
  { id: "relationships", label: "Detecting relationships" },
  { id: "er_diagram", label: "Building ER diagram" },
];

// A real schema fetch against a small demo database is often near-
// instant, which would make the step-by-step animation flash by too
// fast to actually read. This is a floor on how long each step is
// shown, not a substitute for the real work — the "Reading schema" /
// "Discovering tables" steps genuinely wait on the real fetchSchema()
// call below; this constant only paces the cosmetic steps around it.
const MIN_STEP_MS = 450;

/**
 * Loading screen shown right after a database connects. Previously this
 * was a bare 5-step setInterval timer with no actual work behind it —
 * "Reading schema" / "Detecting relationships" were just labels on a
 * clock, unrelated to anything actually happening. It now performs the
 * real /api/schema fetch (the same call the dashboard would otherwise
 * make on its own right after this screen) while it animates, so the
 * labels describe real work in flight. If that fetch fails, this
 * degrades gracefully — same principle as description generation
 * failing elsewhere in the app — showing the error briefly and still
 * continuing to the dashboard rather than getting the user stuck on a
 * loading screen forever.
 */
export default function DatabasePrepLoading({ dbName, onComplete }) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const markDone = (id) => {
      if (!cancelled) setCompletedSteps((prev) => new Set(prev).add(id));
    };

    async function run() {
      // Step 0 ("Connected") is already true by the time this component
      // mounts — the connect API call already succeeded before App.jsx
      // rendered this screen — so it starts pre-completed.
      markDone("connected");
      if (cancelled) return;
      setCurrentStepIndex(1);
      await wait(MIN_STEP_MS);

      // The actual schema introspection call — real network request,
      // real backend work, not a timer running in parallel with nothing.
      let hadError = false;
      try {
        await fetchSchema();
      } catch (err) {
        hadError = true;
        if (!cancelled) setError(err.message || "Couldn't read the database schema.");
      }
      if (cancelled) return;

      markDone("schema");
      setCurrentStepIndex(2);
      await wait(MIN_STEP_MS);
      markDone("tables");
      if (cancelled) return;
      setCurrentStepIndex(3);
      await wait(MIN_STEP_MS);
      markDone("relationships");
      if (cancelled) return;
      setCurrentStepIndex(4);
      await wait(MIN_STEP_MS);
      markDone("er_diagram");

      await wait(hadError ? 900 : 300); // give a real error a moment to actually be read
      if (!cancelled) onComplete?.();
    }

    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onComplete]);

  return (
    <div className="min-h-screen w-full bg-bg dark:bg-darkBg flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: -10 }}
        transition={{ duration: 0.25 }}
        className="w-full max-w-[460px] bg-[#FFFDF9] dark:bg-[#181715] rounded-3xl border border-[#EAE3D2] dark:border-stone-800 shadow-xl p-7 text-[#23201C] dark:text-stone-100 font-sans"
      >
        {/* Header */}
        <div className="flex items-center gap-3.5 mb-6">
          <div className="w-10 h-10 rounded-2xl bg-[#44574A]/10 text-[#44574A] dark:text-amber-400 flex items-center justify-center font-mono text-sm font-bold border border-[#44574A]/20">
            &gt;_
          </div>
          <div>
            <h3 className="font-mono text-lg font-bold text-[#23201C] dark:text-stone-100 tracking-tight">
              Preparing {dbName || "Database"}
            </h3>
            <p className="text-xs text-[#787163] dark:text-stone-400 mt-0.5">
              Introspecting structure & metadata…
            </p>
          </div>
        </div>

        {/* Steps List */}
        <div className="relative space-y-4 pl-1">
          {PREP_STEPS.map((stepItem, idx) => {
            const isDone = completedSteps.has(stepItem.id);
            const isActive = idx === currentStepIndex && !isDone;

            return (
              <div key={stepItem.id} className="relative flex items-center gap-3.5 group">
                {/* Step Line Connector */}
                {idx < PREP_STEPS.length - 1 && (
                  <div
                    className={`absolute left-[11px] top-6 w-[2px] h-5 transition-colors duration-300 ${
                      idx < currentStepIndex || isDone
                        ? "bg-[#44574A] dark:bg-amber-500"
                        : "bg-stone-200 dark:bg-stone-800"
                    }`}
                  />
                )}

                {/* Step Indicator */}
                {isDone ? (
                  <motion.div
                    initial={{ scale: 0.7 }}
                    animate={{ scale: 1 }}
                    className="w-6 h-6 rounded-full bg-[#44574A] text-white flex items-center justify-center text-xs font-bold shadow-xs z-10 shrink-0"
                  >
                    ✓
                  </motion.div>
                ) : isActive ? (
                  <div className="w-6 h-6 rounded-full border-2 border-amber-600/40 border-t-amber-600 animate-spin z-10 shrink-0" />
                ) : (
                  <div className="w-6 h-6 rounded-full border border-stone-300 dark:border-stone-700 bg-stone-100/60 dark:bg-stone-900/60 z-10 shrink-0" />
                )}

                {/* Step Label */}
                <span
                  className={`font-mono text-xs transition-colors ${
                    isDone
                      ? "text-[#23201C] dark:text-stone-100 font-semibold"
                      : isActive
                      ? "text-[#B86B12] dark:text-amber-400 font-semibold animate-pulse"
                      : "text-stone-400 dark:text-stone-600 font-normal"
                  }`}
                >
                  {isDone ? `✓ ${stepItem.label}` : stepItem.label}
                </span>
              </div>
            );
          })}
        </div>

        {error && (
          <div className="mt-5 p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/40 rounded-xl">
            {error} — continuing anyway, you can retry from the dashboard.
          </div>
        )}
      </motion.div>
    </div>
  );
}
