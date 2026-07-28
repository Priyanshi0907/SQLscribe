import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { fetchSchema } from "../lib/api";
import { inferRelationships } from "../lib/schemaRelationships";

const NAV_ITEMS = [
  { key: "new", label: "New Query", icon: "✎" },
  { key: "history", label: "Recent Queries", icon: "🕐" },
  { key: "schema", label: "Schema", icon: "⚏" },
];

function initialsFor(name) {
  if (!name) return "?";
  return name.slice(0, 2).toUpperCase();
}

function DatabaseSummary({ tables }) {
  if (!tables.length) return null;

  const columnCount = tables.reduce((sum, t) => sum + t.columns.length, 0);
  const relationshipCount = inferRelationships(tables).length;
  const rowCount = tables.reduce((sum, t) => sum + (t.row_count || 0), 0);

  const stats = [
    { label: "Tables", value: tables.length },
    { label: "Columns", value: columnCount },
    { label: "Relationships", value: relationshipCount },
    { label: "Rows", value: rowCount.toLocaleString() },
  ];

  return (
    <div className="border border-border dark:border-darkBorder rounded-xl bg-card/60 dark:bg-darkCard/60 p-3 shadow-soft dark:shadow-darkSoft">
      <p className="text-[10px] font-bold tracking-wide text-sqlText/80 dark:text-accent/80 mb-2">
        DATABASE SUMMARY
      </p>
      <div className="grid grid-cols-2 gap-2">
        {stats.map((s) => (
          <div
            key={s.label}
            className="bg-bg dark:bg-darkBg rounded-lg px-2.5 py-2 border border-border/60 dark:border-darkBorder/60"
          >
            <p className="text-[15px] font-extrabold text-[#2B2B2B] dark:text-darkText leading-none">{s.value}</p>
            <p className="text-[10px] text-[#8a8574] dark:text-darkText/50 mt-1">{s.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Sidebar({ activeView, onNavigate, username, onLogout, theme, onToggleTheme }) {
  const [tables, setTables] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [error, setError] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    fetchSchema()
      .then((data) => setTables(data.tables))
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function toggleTable(name) {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  return (
    <motion.aside
      animate={{ width: collapsed ? 76 : 260 }}
      transition={{ type: "spring", stiffness: 300, damping: 32 }}
      className="shrink-0 h-full bg-bg dark:bg-darkBg border-r border-border dark:border-darkBorder flex flex-col overflow-hidden relative z-10"
    >
      <div className="relative px-5 py-4 border-b border-border dark:border-darkBorder flex items-center justify-between">
        <div className="absolute bottom-0 left-0 w-16 h-[2px] bg-gradient-to-r from-accent to-transparent" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-7 h-7 rounded-md bg-terminal text-accent flex items-center justify-center font-mono text-xs font-bold shrink-0 shadow-soft dark:shadow-darkSoft">
            &gt;_
          </span>
          {!collapsed && (
            <span className="font-mono text-lg font-bold text-[#2B2B2B] dark:text-darkText truncate">
              SQL<span className="text-accent">scribe</span>
            </span>
          )}
        </div>
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-[#a39d8a] hover:bg-card dark:hover:bg-darkCard hover:text-[#5A5650] dark:hover:text-darkText transition-colors"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className={`text-[10px] transition-transform ${collapsed ? "rotate-180" : ""}`}>◀</span>
        </button>
      </div>

      <nav className="px-3 pt-3 pb-1 space-y-1 relative">
        {NAV_ITEMS.map((item) => {
          const active = activeView === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              title={collapsed ? item.label : undefined}
              className={`relative w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active ? "text-[#2B2B2B] dark:text-darkText" : "text-[#5A5650] dark:text-darkText/60 hover:bg-card/60 dark:hover:bg-darkCard/60"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="sidebar-active-pill"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                  className="absolute inset-0 bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-lg shadow-soft dark:shadow-darkSoft"
                />
              )}
              <span
                className={`relative w-6 h-6 rounded-md flex items-center justify-center text-[12px] shrink-0 transition-colors ${
                  active ? "bg-accent/15 text-accent" : "text-current"
                }`}
              >
                {item.icon}
              </span>
              {!collapsed && <span className="relative truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {!collapsed && (
        <>
          <div className="px-3 pt-1.5">
            <DatabaseSummary tables={tables} />
          </div>

          <div className="px-5 py-3 mt-2">
            <p className="text-[14px] font-extrabold tracking-wide text-sqlText dark:text-accent">
              DATABASE SCHEMA
            </p>
          </div>

          <div className="flex-1 overflow-y-auto px-3 space-y-1">
            {error && (
              <p className="text-xs text-red-700 dark:text-red-400 px-2">Couldn't load schema: {error}</p>
            )}
            {tables.map((table) => (
              <div key={table.name}>
                <button
                  onClick={() => toggleTable(table.name)}
                  className="w-full flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-card/60 dark:hover:bg-darkCard/60 text-sm text-[#3a382f] dark:text-darkText/80 transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-[#8a8574] dark:text-darkText/40">{expanded[table.name] ? "⌄" : "›"}</span>
                    <span className="w-5 h-5 rounded bg-primary/10 dark:bg-primary/20 text-primary flex items-center justify-center text-[11px] shrink-0">⊞</span>
                    {table.name}
                  </span>
                  <span className="text-[11px] bg-border/70 dark:bg-darkBorder text-[#6b6555] dark:text-darkText/60 rounded-full px-2 py-0.5">
                    {table.columns.length}
                  </span>
                </button>
                {expanded[table.name] && (
                  <ul className="pl-9 pb-1">
                    {table.columns.map((col) => (
                      <li
                        key={col.name}
                        className="text-[11px] font-mono text-[#7a7566] dark:text-darkText/50 py-0.5 flex justify-between pr-2"
                      >
                        <span>{col.name}</span>
                        <span className="text-[#a39d8a] dark:text-darkText/30">{col.type}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </>
      )}
      {collapsed && <div className="flex-1" />}

      <div className="px-3 py-3 border-t border-border dark:border-darkBorder">
        <button
          onClick={onToggleTheme}
          className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm text-[#5A5650] dark:text-darkText/70 hover:bg-card/60 dark:hover:bg-darkCard/60 transition-colors"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          <span className="w-6 h-6 rounded-md bg-accent/10 text-accent flex items-center justify-center text-[13px] shrink-0">
            {theme === "dark" ? "☀" : "☾"}
          </span>
          {!collapsed && <span className="truncate">{theme === "dark" ? "Light mode" : "Dark mode"}</span>}
        </button>
      </div>

      <div className="relative border-t border-border dark:border-darkBorder" ref={menuRef}>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="absolute bottom-full left-3 right-3 mb-2 bg-card dark:bg-darkCard border border-border dark:border-darkBorder rounded-xl shadow-soft dark:shadow-darkSoft overflow-hidden"
          >
            <button
              onClick={() => {
                setMenuOpen(false);
                onLogout();
              }}
              className="w-full text-left px-3 py-2.5 text-sm text-accent hover:bg-bg dark:hover:bg-darkBg transition-colors"
            >
              ↪ Sign out
            </button>
          </motion.div>
        )}
        <button
          onClick={() => setMenuOpen((o) => !o)}
          className="w-full px-4 py-4 flex items-center gap-2.5 hover:bg-card/60 dark:hover:bg-darkCard/60 transition-colors"
        >
          <span className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center text-xs font-semibold shrink-0 ring-2 ring-primary/20">
            {initialsFor(username)}
          </span>
          {!collapsed && (
            <>
              <span className="leading-tight text-left flex-1 min-w-0">
                <span className="block text-sm font-medium text-[#2B2B2B] dark:text-darkText truncate">{username}</span>
                <span className="block text-[11px] text-[#8a8574] dark:text-darkText/50">Signed in</span>
              </span>
              <span className={`text-[10px] text-[#a39d8a] transition-transform ${menuOpen ? "" : "rotate-180"}`}>
                ▲
              </span>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  );
}