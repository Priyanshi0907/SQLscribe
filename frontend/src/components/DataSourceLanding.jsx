import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { connectDemo, connectPostgres, connectMysql, connectSqlitePath, connectSqlite } from "../lib/api";

const ENGINES = [
  { key: "postgres", label: "PostgreSQL", icon: "🐘", defaultPort: "5432" },
  { key: "mysql", label: "MySQL", icon: "🐬", defaultPort: "3306" },
  { key: "sqlite", label: "SQLite", icon: "📄", defaultPort: null },
];

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  show: (i) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.07, duration: 0.3, ease: "easeOut" },
  }),
};

export default function DataSourceLanding({ onConnected }) {
  const [expanded, setExpanded] = useState(null); // "connect" | "upload" | null
  const [engine, setEngine] = useState("postgres");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [dbForm, setDbForm] = useState({ host: "127.0.0.1", port: "5432", database: "", user: "", password: "" });
  const [sqlitePath, setSqlitePath] = useState("");

  const fileInputRef = useRef(null);
  const [fileName, setFileName] = useState(null);

  async function handleDemo() {
    setLoading(true);
    setError(null);
    try {
      const info = await connectDemo();
      onConnected(info);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleEngineChange(nextEngine) {
    setEngine(nextEngine);
    setError(null);
    const nextDefaultPort = ENGINES.find((e) => e.key === nextEngine)?.defaultPort;
    if (nextDefaultPort) setDbForm((f) => ({ ...f, port: nextDefaultPort }));
  }

  async function handleConnectSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      let info;
      if (engine === "postgres") info = await connectPostgres(dbForm);
      else if (engine === "mysql") info = await connectMysql(dbForm);
      else info = await connectSqlitePath(sqlitePath);
      onConnected(info);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setLoading(true);
    setError(null);
    try {
      const info = await connectSqlite(file);
      onConnected(info);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen w-full bg-bg dark:bg-darkBg flex items-center justify-center p-6">
      <div className="w-full max-w-xl">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="text-center mb-8"
        >
          <div className="inline-flex items-center gap-2 mb-3">
            <span className="w-9 h-9 rounded-md bg-terminal text-accent flex items-center justify-center font-mono text-sm font-bold shadow-soft dark:shadow-darkSoft">
              &gt;_
            </span>
            <span className="font-mono text-2xl font-bold text-[#2B2B2B] dark:text-darkText">
              SQL<span className="text-accent">scribe</span>
            </span>
          </div>
          <h1 className="font-mono text-[26px] font-black text-[#2B2B2B] dark:text-darkText tracking-tight">
            Choose your data source
          </h1>
          <p className="text-sm text-[#7a7566] dark:text-darkText/60 mt-1">
            Pick one to unlock the query interface. You can switch later.
          </p>
        </motion.div>

        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="mb-4 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg px-4 py-2.5 overflow-hidden"
          >
            {error}
          </motion.div>
        )}

        <div className="space-y-3">
          {/* Demo database */}
          <motion.button
            custom={0}
            variants={cardVariants}
            initial="hidden"
            animate="show"
            whileHover={{ y: -2 }}
            onClick={handleDemo}
            disabled={loading}
            className="w-full text-left bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-xl p-4 shadow-soft hover:shadow-softHover dark:shadow-darkSoft dark:hover:shadow-darkSoftHover transition-shadow disabled:opacity-50 flex items-center gap-4"
          >
            <span className="w-11 h-11 rounded-lg bg-primary/10 dark:bg-primary/20 flex items-center justify-center text-xl shrink-0">
              📦
            </span>
            <span className="flex-1">
              <span className="block font-mono text-[15px] font-bold text-[#2B2B2B] dark:text-darkText">
                Load Demo Database
              </span>
              <span className="block text-xs text-[#7a7566] dark:text-darkText/60 mt-0.5">
                RetailDB — customers, products, orders. Instant, no setup.
              </span>
            </span>
            <span className="text-[#a39d8a] dark:text-darkText/40">→</span>
          </motion.button>

          {/* Connect Database - PostgreSQL / MySQL / SQLite */}
          <motion.div
            custom={1}
            variants={cardVariants}
            initial="hidden"
            animate="show"
            className="bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-xl overflow-hidden shadow-soft dark:shadow-darkSoft"
          >
            <button
              onClick={() => setExpanded(expanded === "connect" ? null : "connect")}
              className="w-full text-left p-4 hover:bg-bg/40 dark:hover:bg-darkBg/40 hover:-translate-y-0.5 transition-all duration-200 flex items-center gap-4"
            >
              <span className="w-11 h-11 rounded-lg bg-accent/10 dark:bg-accent/20 flex items-center justify-center text-xl shrink-0">
                🔌
              </span>
              <span className="flex-1">
                <span className="block font-mono text-[15px] font-bold text-[#2B2B2B] dark:text-darkText">
                  Connect Database
                </span>
                <span className="block text-xs text-[#7a7566] dark:text-darkText/60 mt-0.5">
                  PostgreSQL, MySQL, or a SQLite file already on the server.
                </span>
              </span>
              <span className={`text-[#a39d8a] dark:text-darkText/40 transition-transform ${expanded === "connect" ? "rotate-90" : ""}`}>
                →
              </span>
            </button>

            {expanded === "connect" && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="px-4 pb-4 border-t border-border dark:border-darkBorder pt-4"
              >
                <div className="flex bg-bg dark:bg-darkBg rounded-lg p-1 mb-3 border border-border dark:border-darkBorder">
                  {ENGINES.map((e) => (
                    <button
                      key={e.key}
                      type="button"
                      onClick={() => handleEngineChange(e.key)}
                      className={`flex-1 flex items-center justify-center gap-1.5 text-xs font-medium rounded-md py-1.5 transition-colors ${e.key === engine ? "bg-card dark:bg-darkCard text-[#2B2B2B] dark:text-darkText shadow-sm" : "text-[#a39d8a] dark:text-darkText/40"
                        }`}
                    >
                      <span>{e.icon}</span> {e.label}
                    </button>
                  ))}
                </div>

                <form onSubmit={handleConnectSubmit} className="space-y-2.5">
                  {engine === "sqlite" ? (
                    <div>
                      <Field
                        label="Filename in backend/data/local_sources/"
                        value={sqlitePath}
                        onChange={setSqlitePath}
                        placeholder="database.sqlite"
                        required
                      />
                      <p className="text-[11px] text-[#a39d8a] dark:text-darkText/40 mt-1.5">
                        For safety, this only looks inside the server's
                        local_sources folder — drop your file there first.
                        Prefer picking a file from your own computer? Use
                        "Upload SQLite Database" instead.
                      </p>
                    </div>
                  ) : (
                    <>
                      <div className="grid grid-cols-[1fr_100px] gap-2.5">
                        <Field label="Host" value={dbForm.host} onChange={(v) => setDbForm({ ...dbForm, host: v })} placeholder="127.0.0.1" />
                        <Field label="Port" value={dbForm.port} onChange={(v) => setDbForm({ ...dbForm, port: v })} placeholder={engine === "mysql" ? "3306" : "5432"} />
                      </div>
                      <Field label="Database" value={dbForm.database} onChange={(v) => setDbForm({ ...dbForm, database: v })} placeholder="mydb" required />
                      <Field label="User" value={dbForm.user} onChange={(v) => setDbForm({ ...dbForm, user: v })} placeholder={engine === "mysql" ? "root" : "postgres"} required />
                      <Field label="Password" type="password" value={dbForm.password} onChange={(v) => setDbForm({ ...dbForm, password: v })} />
                      <p className="text-[11px] text-[#a39d8a] dark:text-darkText/40 leading-relaxed">
                        Use the same database name, username, and password you'd use to
                        connect with {engine === "mysql" ? "the mysql client" : "psql"} directly
                        — the grey example text isn't a real value, it just shows the shape.
                      </p>
                    </>
                  )}
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full mt-1 bg-primary text-white rounded-lg py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
                  >
                    {loading ? "Connecting…" : "Connect"}
                  </button>
                </form>
              </motion.div>
            )}
          </motion.div>

          {/* Upload Database */}
          <motion.div
            custom={2}
            variants={cardVariants}
            initial="hidden"
            animate="show"
            className="bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-xl overflow-hidden shadow-soft dark:shadow-darkSoft"
          >
            <button
              onClick={() => setExpanded(expanded === "upload" ? null : "upload")}
              className="w-full text-left p-4 hover:bg-bg/40 dark:hover:bg-darkBg/40 hover:-translate-y-0.5 transition-all duration-200 flex items-center gap-4"
            >
              <span className="w-11 h-11 rounded-lg bg-sqlText/10 dark:bg-sqlText/20 flex items-center justify-center text-xl shrink-0">
                📁
              </span>
              <span className="flex-1">
                <span className="block font-mono text-[15px] font-bold text-[#2B2B2B] dark:text-darkText">
                  Upload Database
                </span>
                <span className="block text-xs text-[#7a7566] dark:text-darkText/60 mt-0.5">
                  Have a .db or .sqlite file? Drop it in.
                </span>
              </span>
              <span className={`text-[#a39d8a] dark:text-darkText/40 transition-transform ${expanded === "upload" ? "rotate-90" : ""}`}>
                →
              </span>
            </button>

            {expanded === "upload" && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="px-4 pb-4 border-t border-border dark:border-darkBorder pt-4"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".db,.sqlite,.sqlite3"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading}
                  className="w-full border border-dashed border-border dark:border-darkBorder rounded-lg py-4 text-sm text-[#7a7566] dark:text-darkText/60 hover:border-primary/40 hover:text-primary transition-colors disabled:opacity-50"
                >
                  {loading ? "Uploading…" : fileName ? `Selected: ${fileName}` : "Click to choose a file"}
                </button>
              </motion.div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text", required }) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-[#7a7566] dark:text-darkText/60 mb-1">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-border dark:border-darkBorder rounded-lg px-3 py-1.5 text-sm bg-white/70 dark:bg-darkBg text-[#2B2B2B] dark:text-darkText placeholder:text-[#a39d8a] dark:placeholder:text-darkText/30 focus:outline-none focus:border-primary/50"
      />
    </label>
  );
}