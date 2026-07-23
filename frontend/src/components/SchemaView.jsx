import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { fetchSchema } from "../lib/api";
import ERDiagram from "./ERDiagram";

export default function SchemaView() {
  const [tables, setTables] = useState(null);
  const [dbName, setDbName] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSchema()
      .then((data) => {
        setTables(data.tables);
        setDbName(data.database);
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="relative bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-2xl overflow-hidden shadow-soft dark:shadow-darkSoft"
    >
      <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-accent via-accent/50 to-transparent" />
      <div className="p-6">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h1 className="font-mono text-[34px] font-black text-[#2B2B2B] dark:text-darkText tracking-tight">
              Database schema
            </h1>
            <p className="text-sm text-[#7a7566] dark:text-darkText/60 mt-1 mb-6">
              {dbName ? `Live schema for ${dbName}. This is exactly what gets sent to the model as context.` : "Loading schema…"}
            </p>
          </div>
          {dbName && (
            <span className="shrink-0 text-[11px] font-mono text-accent bg-accent/10 border border-accent/20 rounded-full px-3 py-1.5">
              {dbName}
            </span>
          )}
        </div>

        {error && (
          <p className="text-sm text-red-700 dark:text-red-300">Couldn't load schema: {error}</p>
        )}

        {!tables && !error && (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-6 rounded skeleton animate-shimmer" style={{ width: `${80 - i * 10}%` }} />
            ))}
          </div>
        )}

        {tables && (
          <>
            <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent mb-4 flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-accent/15 text-accent flex items-center justify-center text-[10px]">⌗</span>
              ENTITY RELATIONSHIP DIAGRAM
            </p>
            <ERDiagram tables={tables} />
          </>
        )}
      </div>
    </motion.div>
  );
}