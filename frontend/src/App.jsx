import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Sidebar from "./components/Sidebar";
import QueryPanel from "./components/QueryPanel";
import ResultsPanel from "./components/ResultsPanel";
import QueryHistory from "./components/QueryHistory";
import SchemaView from "./components/SchemaView";
import HistoryView from "./components/HistoryView";
import DataSourceLanding from "./components/DataSourceLanding";
import MetaTableReview from "./components/MetaTableReview";
import DatabasePrepLoading from "./components/DatabasePrepLoading";
import ErrorBoundary from "./components/ErrorBoundary";
import AuthScreen from "./components/AuthScreen";
import ConfirmWriteModal from "./components/ConfirmWriteModal";
import { useToast } from "./components/Toast";
import { useTheme } from "./lib/useTheme";
import {
  runQuery, confirmQuery, fetchHistory, deleteHistoryEntry, clearHistory as apiClearHistory,
  setHistoryFavorite, fetchSource, disconnectSource, fetchMe, getToken, clearToken,
  logout as apiLogout,
} from "./lib/api";

const screenVariants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const showToast = useToast();

  const [checkingAuth, setCheckingAuth] = useState(true);
  const [username, setUsername] = useState(null);
  // True only for the span between an explicit sign-in/sign-up action and
  // landing on the data-source picker. Distinguishes "the user just
  // authenticated" from "a saved token resumed an existing session on
  // page load" — see the effect below for why that distinction matters.
  const [freshAuth, setFreshAuth] = useState(false);

  const [checkingSource, setCheckingSource] = useState(false);
  const [source, setSource] = useState(null); // { type, name, dialect } | null
  // True for the span between a fresh connect (demo/upload/live DB) and
  // the user clicking through the meta-table description review screen.
  // Only fresh connects show this — reattaching to an already-connected
  // source on page reload (see the fetchSource effect below) skips
  // straight to the dashboard, same as it always did.
  const [awaitingMetaReview, setAwaitingMetaReview] = useState(false);
  const [prepLoading, setPrepLoading] = useState(false);

  const [activeView, setActiveView] = useState("new");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const [sessionKey, setSessionKey] = useState(0);
  // A generated INSERT/UPDATE/DELETE/DDL statement waiting on an explicit
  // user confirmation before it's executed — { question, sql, dialect } | null.
  const [pendingWrite, setPendingWrite] = useState(null);
  // Bumped every time a query actually executes (read or write). Sidebar and
  // SchemaView both key their schema fetch off this so a DROP/CREATE/ALTER
  // (or any DML that changes row counts) is reflected immediately, instead
  // of only refreshing on the next full page load.
  const [schemaVersion, setSchemaVersion] = useState(0);

  // On load, check whether we already have a valid session (e.g. the user
  // refreshed the page) so we don't force a re-login unnecessarily.
  useEffect(() => {
    if (!getToken()) {
      setCheckingAuth(false);
      return;
    }
    fetchMe()
      .then((data) => setUsername(data.username))
      .catch(() => clearToken()) // stored token is stale/invalid — drop it
      .finally(() => setCheckingAuth(false));
  }, []);

  // Once signed in, check whether a data source is already active too —
  // but only when resuming an existing session (page reload). A fresh
  // sign-in or sign-up always lands on the picker: the backend's active
  // connection is a single shared value, not scoped to a particular
  // login, so silently reattaching to "whatever was last connected" would
  // skip the choice entirely and feel like the app ignored the button
  // they just clicked.
  useEffect(() => {
    if (!username) return;
    if (freshAuth) {
      setCheckingSource(false);
      return;
    }
    setCheckingSource(true);
    fetchSource()
      .then((info) => {
        if (info.connected) setSource(info);
      })
      .catch((err) => {
        if (err.status === 401) handleSessionExpired();
      })
      .finally(() => setCheckingSource(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, freshAuth]);

  const loadHistory = useCallback(() => {
    if (!source) return;
    fetchHistory(10, source.name)
      .then((data) => setHistory(data.history))
      .catch(() => {
        // history is a nice-to-have panel; a failed fetch shouldn't block the app
      });
  }, [source]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);


  async function handleRun(question) {
    setLoading(true);
    setError(null);
    setPendingWrite(null);
    try {
      const data = await runQuery(question);
      if (data.pending_confirmation) {
        // A write query was generated and validated, but nothing has run
        // yet — show it to the user and wait for an explicit confirm.
        setResult(data);
        setPendingWrite({ question, sql: data.sql, dialect: data.dialect });
        return;
      }
      setResult(data);
      if (data.truncated) {
        showToast(
          `Showing the first ${data.row_count.toLocaleString()} rows — the full result set is larger. Try narrowing your question.`,
          "info",
          6000
        );
      }
      loadHistory(); // this run created exactly one new, real history entry
      setSchemaVersion((v) => v + 1); // schema/row counts may have changed — refetch
    } catch (err) {
      if (err.status === 401) return handleSessionExpired();
      setError(err.message);
      setResult(null);
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmWrite() {
    if (!pendingWrite) return;
    try {
      const data = await confirmQuery(pendingWrite.question, pendingWrite.sql);
      setResult(data);
      setPendingWrite(null);
      showToast("Query executed successfully.", "success");
      loadHistory();
      setSchemaVersion((v) => v + 1); // this is the path DDL/DML writes actually run through
    } catch (err) {
      if (err.status === 401) return handleSessionExpired();
      setPendingWrite(null);
      setError(err.message);
      showToast(err.message, "error");
    }
  }

  function handleCancelWrite() {
    // Nothing was ever executed — just drop the pending statement and let
    // the user try a different question.
    setPendingWrite(null);
    showToast("Query cancelled — nothing was changed.", "info");
  }

  function handleNavigate(view) {
    if (view === "new") {
      // "New Query" always starts a fresh session, even if you're
      // already on this tab — clears the question, SQL, and results.
      setResult(null);
      setError(null);
      setPendingWrite(null);
      setPendingQuestion("");
      setSessionKey((k) => k + 1);
    }
    setActiveView(view);
  }

  // Clicking a past query just displays what's already stored for it —
  // no API call, no new history entry. Nothing is re-run.
  function handleViewHistoryItem(item) {
    setPendingQuestion(item.question);
    setPendingWrite(null);
    setResult({
      sql: item.sql_text,
      columns: item.columns,
      rows: item.rows,
      row_count: item.row_count,
      elapsed_ms: item.elapsed_ms,
      validated: true,
      dialect: item.dialect,
      read_only: true,
    });
    setError(null);
    setSessionKey((k) => k + 1);
    setActiveView("new");
  }

  async function handleDeleteHistoryItem(id) {
    const previous = history;
    setHistory((prev) => prev.filter((h) => h.id !== id));
    try {
      await deleteHistoryEntry(id);
    } catch (err) {
      if (err.status === 401) return handleSessionExpired();
      setHistory(previous); // roll back — the delete didn't actually happen
      showToast("Couldn't delete that entry. Please try again.", "error");
    }
  }

  async function handleToggleFavorite(id, nextValue) {
    setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, is_favorite: nextValue } : h)));
    try {
      await setHistoryFavorite(id, nextValue);
    } catch (err) {
      if (err.status === 401) return handleSessionExpired();
      // revert the optimistic flip
      setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, is_favorite: !nextValue } : h)));
      showToast("Couldn't update that pin. Please try again.", "error");
    }
  }

  async function handleClearHistory() {
    try {
      await apiClearHistory(source?.name);
      setHistory([]);
      showToast("History cleared.", "success");
    } catch (err) {
      if (err.status === 401) handleSessionExpired();
    }
  }


  function handleAuthenticated(name) {
    setFreshAuth(true);
    setUsername(name);
  }

  async function handleLogout() {
    try {
      await apiLogout();
    } catch {
      // clearToken() already ran inside apiLogout regardless of outcome
    }
    resetAllState();
  }

  function handleSessionExpired() {
    clearToken();
    resetAllState();
    showToast("Your session expired — please sign in again.", "info");
  }

  function resetAllState() {
    setUsername(null);
    setFreshAuth(false);
    setSource(null);
    setAwaitingMetaReview(false);
    setResult(null);
    setError(null);
    setPendingWrite(null);
    setHistory([]);
    setActiveView("new");
  }

  function handleConnected(info) {
    setSource(info);
    setFreshAuth(false); // the picker's job is done for this session
    setPrepLoading(true); // show the 5s database prep loading screen on simple background
    setAwaitingMetaReview(true); // show the description review modal over dashboard after prep
  }

  function handleContinueFromMetaReview() {
    setAwaitingMetaReview(false);
    setResult(null);
    setError(null);
    setPendingWrite(null);
    setPendingQuestion("");
    setSessionKey((k) => k + 1);
    setActiveView("new");
    showToast(`Connected to ${source?.name}.`, "success");
  }

  async function handleSwitchDatabase() {
    try {
      await disconnectSource();
    } catch {
      // even if the disconnect call fails, drop back to the landing
      // screen locally — the next connect call will overwrite state anyway
    }
    setSource(null);
    setAwaitingMetaReview(false);
    setPrepLoading(false);
    setResult(null);
    setError(null);
    setPendingWrite(null);
    setHistory([]);
  }

  let screenKey = "loading";
  if (!checkingAuth) {
    if (!username) screenKey = "auth";
    else if (checkingSource) screenKey = "loading";
    else if (!source) screenKey = "landing";
    else if (prepLoading) screenKey = "prepLoading";
    else screenKey = "dashboard";
  }

  return (
    <AnimatePresence mode="wait">
      {screenKey === "loading" && (
        <motion.div
          key="loading"
          variants={screenVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          className="h-screen w-full bg-bg dark:bg-darkBg flex items-center justify-center"
        >
          <span className="w-6 h-6 border-2 border-border dark:border-darkBorder border-t-accent rounded-full animate-spin" />
        </motion.div>
      )}

      {screenKey === "auth" && (
        <motion.div key="auth" variants={screenVariants} initial="initial" animate="animate" exit="exit">
          <AuthScreen onAuthenticated={handleAuthenticated} />
        </motion.div>
      )}

      {screenKey === "landing" && (
        <motion.div key="landing" variants={screenVariants} initial="initial" animate="animate" exit="exit">
          <DataSourceLanding onConnected={handleConnected} />
        </motion.div>
      )}

      {screenKey === "prepLoading" && (
        <motion.div key="prepLoading" variants={screenVariants} initial="initial" animate="animate" exit="exit">
          <DatabasePrepLoading dbName={source?.name} onComplete={() => setPrepLoading(false)} />
        </motion.div>
      )}

      {screenKey === "dashboard" && (
        <motion.div
          key="dashboard"
          variants={screenVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          className="flex h-screen w-full bg-bg dark:bg-darkBg overflow-hidden"
        >
          <Sidebar
            activeView={activeView}
            onNavigate={handleNavigate}
            username={username}
            onLogout={handleLogout}
            theme={theme}
            onToggleTheme={toggleTheme}
            schemaVersion={schemaVersion}
          />

          <main className="flex-1 overflow-y-auto p-8">
            <div className="max-w-[1400px] mx-auto">
              <ErrorBoundary>
                {activeView === "schema" && <SchemaView schemaVersion={schemaVersion} />}

                {activeView === "history" && (
                  <HistoryView
                    dbName={source?.name}
                    onSelect={handleViewHistoryItem}
                    onDelete={handleDeleteHistoryItem}
                    onToggleFavorite={handleToggleFavorite}
                    onClearAll={handleClearHistory}
                  />
                )}

                {activeView === "new" && (
                  <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-6">
                    <QueryPanel
                      key={sessionKey}
                      onRun={handleRun}
                      loading={loading}
                      result={result}
                      error={error}
                      dbName={source.name}
                      onSwitchDatabase={handleSwitchDatabase}
                      initialQuestion={pendingQuestion}
                    />
                    <ResultsPanel result={result} loading={loading} error={error} />

                    <div className="lg:col-span-2">
                      <QueryHistory
                        items={history}
                        onSelect={handleViewHistoryItem}
                        onDelete={handleDeleteHistoryItem}
                        onToggleFavorite={handleToggleFavorite}
                        onViewAll={() => setActiveView("history")}
                      />
                    </div>
                  </div>
                )}
              </ErrorBoundary>
            </div>
          </main>

          <ConfirmWriteModal
            open={!!pendingWrite}
            sql={pendingWrite?.sql}
            dialect={pendingWrite?.dialect}
            onConfirm={handleConfirmWrite}
            onCancel={handleCancelWrite}
          />

          <MetaTableReview
            isOpen={awaitingMetaReview}
            dbName={source?.name}
            onContinue={handleContinueFromMetaReview}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}