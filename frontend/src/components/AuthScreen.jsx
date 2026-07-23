import { useState } from "react";
import { motion } from "framer-motion";
import { login, signup } from "../lib/api";

const USERNAME_RE = /^[a-zA-Z0-9_.-]{3,32}$/;

const FEATURES = [
  { icon: "💬", title: "Ask in plain English", desc: "No SQL knowledge needed — just describe what you want to know." },
  { icon: "🛡", title: "Read-only, always", desc: "Every generated query is validated before it ever touches your data." },
  { icon: "⚡", title: "Any database", desc: "SQLite, PostgreSQL, or MySQL — connect in seconds." },
];

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const usernameInvalid = mode === "signup" && username.length > 0 && !USERNAME_RE.test(username);
  const passwordTooShort = mode === "signup" && password.length > 0 && password.length < 8;

  async function handleSubmit(e) {
    e.preventDefault();
    if (usernameInvalid || passwordTooShort) return;
    setLoading(true);
    setError(null);
    try {
      const data = mode === "signin"
        ? await login(username, password)
        : await signup(username, password);
      onAuthenticated(data.username);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode);
    setError(null);
  }

  return (
    <div className="min-h-screen w-full bg-bg dark:bg-darkBg flex items-center justify-center p-6 relative overflow-hidden">
      {/* Soft ambient glow, subtle in both themes */}
      <div className="pointer-events-none absolute -top-40 -left-40 w-96 h-96 rounded-full bg-primary/10 dark:bg-primary/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 w-96 h-96 rounded-full bg-accent/10 dark:bg-accent/20 blur-3xl" />

      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="relative w-full max-w-4xl grid md:grid-cols-2 rounded-3xl overflow-hidden shadow-xl border border-border dark:border-darkBorder"
      >
        {/* Left panel — hidden on small screens, sets the tone on desktop */}
        <div className="hidden md:flex flex-col justify-between bg-terminal text-[#e4e0d6] p-10 relative overflow-hidden">
          {/* Blueprint dot-grid, the same "canvas" texture as the ERDiagram,
              so the auth screen and schema view feel like one product. */}
          <div
            className="absolute inset-0 text-white/[0.06] pointer-events-none"
            style={{
              backgroundImage: "radial-gradient(currentColor 1px, transparent 1px)",
              backgroundSize: "20px 20px",
            }}
          />
          <div className="pointer-events-none absolute -top-24 -right-24 w-72 h-72 rounded-full bg-accent/10 blur-3xl" />

          <div className="relative">
            <div className="inline-flex items-center gap-2 mb-8">
              <span className="w-9 h-9 rounded-md bg-accent/20 text-accent flex items-center justify-center font-mono text-sm font-bold border border-accent/30">
                &gt;_
              </span>
              <span className="font-mono text-xl font-bold text-white">
                SQL<span className="text-accent">scribe</span>
              </span>
            </div>
            <h2 className="font-mono text-2xl font-black text-white leading-snug mb-3">
              Talk to your database
              <br />like it's a person.
            </h2>
            <p className="text-sm text-[#a9a496] leading-relaxed">
              Ask questions in plain English, get validated SQL and real
              results back — instantly.
            </p>
          </div>

          <div className="relative space-y-5 mt-10">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex items-start gap-3">
                <span className="w-8 h-8 rounded-lg bg-accent/15 border border-accent/20 flex items-center justify-center text-[15px] shrink-0">
                  {f.icon}
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">{f.title}</p>
                  <p className="text-xs text-[#9c9689] mt-0.5 leading-relaxed">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel — the actual form */}
        <div className="relative bg-card dark:bg-darkCard p-8 sm:p-10 flex flex-col justify-center">
          <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-primary via-accent to-transparent" />

          <div className="md:hidden text-center mb-6">
            <div className="inline-flex items-center gap-2 mb-3">
              <span className="w-9 h-9 rounded-md bg-terminal text-accent flex items-center justify-center font-mono text-sm font-bold">
                &gt;_
              </span>
              <span className="font-mono text-2xl font-bold text-[#2B2B2B] dark:text-darkText">
                SQL<span className="text-accent">scribe</span>
              </span>
            </div>
            <p className="text-sm text-[#7a7566] dark:text-darkText/60">Text-to-SQL Assistant</p>
          </div>

          <div className="flex bg-bg dark:bg-darkBg rounded-lg p-1 mb-6 border border-border dark:border-darkBorder relative">
            {["signin", "signup"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => switchMode(m)}
                className={`relative flex-1 text-sm font-medium rounded-md py-1.5 transition-colors z-10 ${
                  mode === m ? "text-[#2B2B2B] dark:text-darkBg" : "text-[#7a7566] dark:text-darkText/50"
                }`}
              >
                {m === "signin" ? "Sign in" : "Sign up"}
              </button>
            ))}
            <motion.div
              layout
              transition={{ type: "spring", stiffness: 500, damping: 35 }}
              className="absolute inset-y-1 w-[calc(50%-4px)] bg-card dark:bg-darkText rounded-md shadow-sm"
              style={
                mode === "signin"
                  ? { left: 4 }
                  : { right: 4 }
              }
            />
          </div>

          <h1 className="font-mono text-[22px] font-extrabold text-[#2B2B2B] dark:text-darkText mb-1">
            {mode === "signin" ? "Welcome back" : "Create your account"}
          </h1>
          <p className="text-xs text-[#7a7566] dark:text-darkText/60 mb-5">
            {mode === "signin"
              ? "Sign in to pick up where you left off."
              : "Takes a few seconds — no email required."}
          </p>

          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className="mb-4 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg px-3 py-2 overflow-hidden"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <label className="block">
              <span className="block text-[11px] font-medium text-[#7a7566] dark:text-darkText/60 mb-1">
                Username
              </span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="pri"
                required
                autoFocus
                className={`w-full border rounded-lg px-3 py-2.5 text-sm bg-white/70 dark:bg-darkBg text-[#2B2B2B] dark:text-darkText placeholder:text-[#a39d8a] dark:placeholder:text-darkText/30 focus:outline-none transition-colors ${
                  usernameInvalid
                    ? "border-red-300 dark:border-red-900 focus:border-red-400"
                    : "border-border dark:border-darkBorder focus:border-primary/60"
                }`}
              />
              {usernameInvalid && (
                <span className="block text-[11px] text-red-600 dark:text-red-400 mt-1">
                  3–32 characters: letters, numbers, underscore, dot, or dash.
                </span>
              )}
            </label>
            <label className="block">
              <span className="block text-[11px] font-medium text-[#7a7566] dark:text-darkText/60 mb-1">
                Password
              </span>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === "signup" ? "At least 8 characters" : "••••••••"}
                  required
                  minLength={mode === "signup" ? 8 : undefined}
                  className={`w-full border rounded-lg pl-3 pr-9 py-2.5 text-sm bg-white/70 dark:bg-darkBg text-[#2B2B2B] dark:text-darkText placeholder:text-[#a39d8a] dark:placeholder:text-darkText/30 focus:outline-none transition-colors ${
                    passwordTooShort
                      ? "border-red-300 dark:border-red-900 focus:border-red-400"
                      : "border-border dark:border-darkBorder focus:border-primary/60"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-[#a39d8a] dark:text-darkText/50 hover:text-[#5A5650] dark:hover:text-darkText"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "🙈" : "👁"}
                </button>
              </div>
              {passwordTooShort && (
                <span className="block text-[11px] text-red-600 dark:text-red-400 mt-1">
                  Password must be at least 8 characters.
                </span>
              )}
            </label>

            <motion.button
              type="submit"
              disabled={loading}
              whileTap={{ scale: 0.98 }}
              whileHover={{ scale: loading ? 1 : 1.01 }}
              className="w-full mt-2 bg-primary text-white rounded-lg py-2.5 text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
            >
              {loading
                ? (mode === "signin" ? "Signing in…" : "Creating account…")
                : (mode === "signin" ? "Sign in" : "Create account")}
            </motion.button>
          </form>

          <p className="text-center text-xs text-[#a39d8a] dark:text-darkText/40 mt-6">
            {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => switchMode(mode === "signin" ? "signup" : "signin")}
              className="text-accent font-medium hover:underline"
            >
              {mode === "signin" ? "Create an account" : "Sign in instead"}
            </button>
          </p>
        </div>
      </motion.div>
    </div>
  );
}