import { useEffect, useRef, useState } from "react";
import { fetchHealth } from "../lib/api";

const POLL_INTERVAL_MS = 15000;

// This pings /api/health, which only proves the FastAPI process is up —
// it says nothing about whether a data source is connected (that's what
// DatabaseSelector is for). The labels below are worded to reflect that,
// so "Backend online" here can't be misread as "your database is
// connected" the way the old "Connected to database" copy could.
const STATUS_CONFIG = {
  connecting: { label: "Checking backend…", dot: "bg-[#e0b25a]", ring: "border-[#e0b25a]/30", text: "text-[#8a6a2a]", bg: "bg-[#e0b25a]/10" },
  connected: { label: "Backend online", dot: "bg-[#4caf58]", ring: "border-[#4caf58]/30", text: "text-[#2f6b36]", bg: "bg-[#4caf58]/10" },
  disconnected: { label: "Backend unreachable", dot: "bg-[#d6564c]", ring: "border-[#d6564c]/30", text: "text-[#a63a31]", bg: "bg-[#d6564c]/10" },
};

export default function ConnectionStatus() {
  const [status, setStatus] = useState("connecting");
  const timerRef = useRef(null);

  async function check() {
    try {
      await fetchHealth();
      setStatus("connected");
    } catch {
      setStatus("disconnected");
    }
  }

  useEffect(() => {
    check();
    timerRef.current = setInterval(check, POLL_INTERVAL_MS);
    return () => clearInterval(timerRef.current);
  }, []);

  const cfg = STATUS_CONFIG[status];

  return (
    <span
      className={`flex items-center gap-1.5 text-xs rounded-full px-3 py-1.5 border ${cfg.bg} ${cfg.ring} ${cfg.text}`}
      title={status === "disconnected" ? "The API server at the configured URL isn't responding." : "The API server is reachable. Database connection status is shown separately."}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${status === "connecting" ? "animate-pulse" : ""}`} />
      {cfg.label}
    </span>
  );
}