import { useLayoutEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { inferRelationships } from "../lib/schemaRelationships";

// `gap` pulls the connector's start/end a few px away from the table
// border into the surrounding whitespace, so the line and its arrowhead
// never sit on top of a card's border or its top accent bar.
function edgePoints(fromRect, toRect, gap = 6) {
  const fromCenter = { x: fromRect.x + fromRect.width / 2, y: fromRect.y + fromRect.height / 2 };
  const toCenter = { x: toRect.x + toRect.width / 2, y: toRect.y + toRect.height / 2 };
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  const vertical = Math.abs(dy) > Math.abs(dx);

  if (vertical) {
    return dy > 0
      ? { start: { x: fromCenter.x, y: fromRect.y + fromRect.height + gap }, end: { x: toCenter.x, y: toRect.y - gap }, axis: "v" }
      : { start: { x: fromCenter.x, y: fromRect.y - gap }, end: { x: toCenter.x, y: toRect.y + toRect.height + gap }, axis: "v" };
  }
  return dx > 0
    ? { start: { x: fromRect.x + fromRect.width + gap, y: fromCenter.y }, end: { x: toRect.x - gap, y: toCenter.y }, axis: "h" }
    : { start: { x: fromRect.x - gap, y: fromCenter.y }, end: { x: toRect.x + toRect.width + gap, y: toCenter.y }, axis: "h" };
}

// Smooth S-curve trace between two edge points, like a routed PCB trace
// rather than a bare straight line — reads much better once more than
// one or two relationships are on screen at once.
function tracePath(start, end, axis) {
  const pull = axis === "v"
    ? Math.max(24, Math.abs(end.y - start.y) * 0.45)
    : Math.max(24, Math.abs(end.x - start.x) * 0.45);
  const c1 = axis === "v" ? { x: start.x, y: start.y + Math.sign(end.y - start.y || 1) * pull } : { x: start.x + Math.sign(end.x - start.x || 1) * pull, y: start.y };
  const c2 = axis === "v" ? { x: end.x, y: end.y - Math.sign(end.y - start.y || 1) * pull } : { x: end.x - Math.sign(end.x - start.x || 1) * pull, y: end.y };
  return {
    d: `M${start.x},${start.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${end.x},${end.y}`,
    // cubic bezier midpoint at t=0.5
    mid: {
      x: 0.125 * (start.x + 3 * c1.x + 3 * c2.x + end.x),
      y: 0.125 * (start.y + 3 * c1.y + 3 * c2.y + end.y),
    },
  };
}

export default function ERDiagram({ tables }) {
  const containerRef = useRef(null);
  const boxRefs = useRef({});
  const [rects, setRects] = useState({});
  const relationships = inferRelationships(tables);

  // Fewer tables means fewer, wider columns so boxes stretch to fill the
  // panel instead of clumping in one corner with a wall of empty space.
  // 1-2 tables -> 1 column (full width), 3-4 -> 2 columns, 5+ -> 3 columns.
  const columnCount = tables.length <= 2 ? 1 : tables.length <= 4 ? 2 : 3;

  // Columns that participate in a relationship (excluding the primary key,
  // which already gets its own 🔑 treatment) get a small accent tick so the
  // table body visually cross-references the traces above it.
  const linkedColumns = new Set();
  relationships.forEach((rel) => {
    linkedColumns.add(`${rel.from}::${rel.column}`);
    linkedColumns.add(`${rel.to}::${rel.column}`);
  });

  useLayoutEffect(() => {
    function measure() {
      if (!containerRef.current) return;
      const containerBox = containerRef.current.getBoundingClientRect();
      const next = {};
      Object.entries(boxRefs.current).forEach(([name, el]) => {
        if (!el) return;
        const box = el.getBoundingClientRect();
        next[name] = {
          x: box.left - containerBox.left,
          y: box.top - containerBox.top,
          width: box.width,
          height: box.height,
        };
      });
      setRects(next);
    }
    measure();
    const timer = setTimeout(measure, 150); // catch late font/layout shifts
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
      clearTimeout(timer);
    };
  }, [tables, columnCount]);

  return (
    // The diagram gets its own framed "sheet" — a subtle border + tinted
    // fill distinguishes it as a canvas rather than boxes floating loose
    // on the page, and the dot grid reads as blueprint paper underneath.
    <div className="relative rounded-xl border border-border/70 dark:border-darkBorder/60 bg-black/[0.015] dark:bg-white/[0.02] p-10 overflow-hidden">
      <div
        ref={containerRef}
        className="relative"
      >
        <div
          className="absolute -inset-10 text-border/70 dark:text-darkBorder/50 pointer-events-none"
          style={{
            backgroundImage: "radial-gradient(currentColor 1px, transparent 1px)",
            backgroundSize: "18px 18px",
          }}
        />

        {/* z-20 — must render ABOVE the table boxes (which are z-10 below).
            Previously this layer had no z-index at all, so any relationship
            line/label sitting near a table's edge got silently clipped
            behind that table's opaque background (e.g. the orders <->
            order_items "order_id" label). Endpoints are inset from the
            box edges (see edgePoints' `gap`) so no line or arrowhead ever
            overlaps a card's border or its top accent bar. */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-20" overflow="visible">
          <defs>
            <marker id="erd-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M1 1L9 5L1 9" fill="none" stroke="#B88746" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </marker>
            <filter id="erd-label-shadow" x="-40%" y="-40%" width="180%" height="220%">
              <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodColor="#7A5230" floodOpacity="0.18" />
            </filter>
          </defs>
          {relationships.map((rel, i) => {
            const fromRect = rects[rel.from];
            const toRect = rects[rel.to];
            if (!fromRect || !toRect) return null;
            const { start, end, axis } = edgePoints(fromRect, toRect);
            const { d, mid } = tracePath(start, end, axis);
            const labelWidth = rel.column.length * 6 + 24;
            const pathId = `erd-path-${i}`;
            return (
              <g key={i}>
                {/* connection pad — small circuit-trace-style terminal at the start */}
                <circle cx={start.x} cy={start.y} r="2.5" fill="#B88746" />
                <path id={pathId} d={d} fill="none" stroke="#B88746" strokeWidth="1.5" markerEnd="url(#erd-arrow)" />
                {/* Signature touch: a small glow pulses along the live relationship,
                    a nod to data actually flowing between these foreign keys. */}
                <circle r="2.4" fill="#B88746" opacity="0.85">
                  <animateMotion dur="2.6s" begin={`${i * 0.35}s`} repeatCount="indefinite">
                    <mpath href={`#${pathId}`} />
                  </animateMotion>
                  <animate attributeName="opacity" values="0;0.9;0" dur="2.6s" begin={`${i * 0.35}s`} repeatCount="indefinite" />
                </circle>
                <g filter="url(#erd-label-shadow)">
                  <rect
                    x={mid.x - labelWidth / 2} y={mid.y - 9}
                    width={labelWidth} height={18} rx={9}
                    fill="#FFFDF9" stroke="#D9C9A8" strokeWidth="1"
                    className="dark:fill-darkCard dark:stroke-darkBorder"
                  />
                </g>
                <text
                  x={mid.x} y={mid.y + 4} textAnchor="middle"
                  fontSize="10" fontFamily="ui-monospace, monospace" fontWeight="600" fill="#7A5230"
                  className="dark:fill-accent"
                >
                  <tspan opacity="0.6">⋈ </tspan>{rel.column}
                </text>
              </g>
            );
          })}
        </svg>

        <div
          className="relative grid gap-x-28 gap-y-14"
          style={{ gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }}
        >
          {tables.map((table, i) => (
            <motion.div
              key={table.name}
              ref={(el) => (boxRefs.current[table.name] = el)}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
              className="group w-full rounded-lg bg-bg dark:bg-darkBg overflow-hidden relative z-10 text-[11px] border border-border dark:border-darkBorder shadow-soft dark:shadow-darkSoft hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
            >
              <div className="h-[3px] bg-gradient-to-r from-accent via-accent/60 to-transparent" />
              <div className="bg-bg dark:bg-darkBg px-3.5 py-2.5 border-b border-border dark:border-darkBorder flex items-center justify-between">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-4 h-4 rounded-[3px] bg-accent/15 text-accent flex items-center justify-center text-[10px] shrink-0">⊞</span>
                  <span className="font-mono text-[12.5px] font-bold text-[#2B2B2B] dark:text-darkText truncate tracking-tight">{table.name}</span>
                </span>
                <span className="text-[9px] font-mono text-[#a39d8a] dark:text-darkText/40 shrink-0 pl-2 whitespace-nowrap">
                  {table.columns.length} col{table.columns.length === 1 ? "" : "s"}
                  {typeof table.row_count === "number" && (
                    <> · {table.row_count.toLocaleString()} row{table.row_count === 1 ? "" : "s"}</>
                  )}
                </span>
              </div>
              <ul>
                {table.columns.map((col, ci) => {
                  const isPk = ci === 0;
                  const isLinked = !isPk && linkedColumns.has(`${table.name}::${col.name}`);
                  return (
                    <li
                      key={col.name}
                      className={`px-3.5 py-[3px] font-mono flex items-center gap-1.5 justify-between border-l-2 transition-colors ${
                        isPk
                          ? "border-l-accent bg-accent/[0.08] text-accent font-semibold"
                          : isLinked
                          ? "border-l-accent/30 text-[#5A5650] dark:text-darkText/70 hover:bg-card/60 dark:hover:bg-darkCard/40"
                          : "border-l-transparent text-[#5A5650] dark:text-darkText/70 hover:bg-card/60 dark:hover:bg-darkCard/40"
                      }`}
                    >
                      <span className="truncate flex items-center gap-1.5">
                        {isPk ? "🔑" : isLinked ? <span className="w-1 h-1 rounded-full bg-accent/50 shrink-0" /> : null}
                        {col.name}
                      </span>
                      <span className="text-[#a39d8a] shrink-0 text-[10px]">{col.type}</span>
                    </li>
                  );
                })}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}