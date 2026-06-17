"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ArrowDown } from "lucide-react";
import type { DecisionKind, DecisionLogEntry } from "@/lib/api";
import { cn, formatClock } from "@/lib/utils";
import { EASE } from "@/components/motion";

const KIND_META: Record<DecisionKind, { label: string; dot: string; ink: string }> = {
  hydration: { label: "MEM", dot: "bg-log-memory", ink: "text-log-memory" },
  route: { label: "ROUTE", dot: "bg-log-route", ink: "text-log-route" },
  expert_spawn: { label: "EXPERT", dot: "bg-log-expert", ink: "text-log-expert" },
  tool_call: { label: "TOOL", dot: "bg-log-tool", ink: "text-log-tool" },
  observation: { label: "OBS", dot: "bg-faint", ink: "text-faint" },
  answer: { label: "ANSWER", dot: "bg-log-answer", ink: "text-foreground" },
  warning: { label: "WARN", dot: "bg-warning", ink: "text-warning" },
  error: { label: "ERROR", dot: "bg-destructive", ink: "text-destructive" },
};

/**
 * One transcript line. Set like a printed ledger: the timestamp lives in the
 * margin, a struck rule (the spine) runs down the gutter, and the kind tick
 * sits on the rule like a bullet. Each line prints itself once on mount —
 * which, on a live run, means every entry types in as it arrives.
 */
function LogEntry({ entry, live }: { entry: DecisionLogEntry; live: boolean }) {
  const reduce = useReducedMotion();
  const meta = KIND_META[entry.kind];
  const flagged = entry.kind === "warning" || entry.kind === "error";
  // the payoff line — the draft landing gets the ignition treatment
  const major = entry.kind === "answer";

  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, y: 7 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: EASE }}
      className={cn(
        "group grid grid-cols-[2.9rem_1fr] sm:grid-cols-[3.6rem_1fr]",
        major && !reduce && "animate-ignite rounded-sm",
      )}
    >
      {/* margin — the transcript's timestamp column */}
      <span className="select-none pr-2 pt-2 text-right text-[10.5px] leading-tight text-faint/80 tabular">
        {formatClock(entry.ts)}
      </span>

      {/* content — bordered left to form the continuous spine rule */}
      <div
        className={cn(
          "relative border-l pb-3 pl-4 pt-2",
          flagged ? "border-l-current" : "border-border",
          entry.kind === "warning" && "text-warning",
          entry.kind === "error" && "text-destructive",
        )}
      >
        {/* the kind tick, sitting on the spine like a bullet on a rule */}
        <span
          className={cn(
            "absolute rounded-full ring-4 ring-surface",
            major ? "-left-[5.5px] top-[10px] size-[11px]" : "-left-[4.5px] top-[11px] size-[9px]",
            meta.dot,
            live && !major && "animate-pulse-dot",
          )}
          aria-hidden
        />
        <p className="flex items-baseline gap-2">
          <span className={cn("shrink-0 font-mono text-[10px] font-semibold uppercase tracking-[0.16em]", flagged ? "" : meta.ink)}>
            {meta.label}
          </span>
        </p>
        <p
          className={cn(
            "mt-1 font-mono leading-snug text-foreground",
            major ? "text-[13px] font-semibold" : "text-[12.5px]",
          )}
        >
          {entry.title}
        </p>
        {entry.detail && (
          <p className="mt-1 font-mono text-[11.5px] leading-snug text-muted-foreground">
            {entry.detail}
          </p>
        )}
        {entry.meta && (
          <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
            {Object.entries(entry.meta).map(([k, v]) => (
              <span key={k} className="font-mono text-[10.5px] text-faint">
                {k}=<span className="text-muted-foreground">{v}</span>
              </span>
            ))}
          </p>
        )}
      </div>
    </motion.li>
  );
}

export function DecisionLog({
  entries,
  live,
  className,
}: {
  entries: DecisionLogEntry[];
  live: boolean;
  className?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  // mirror `pinned` into state so the "jump to live" affordance can render —
  // it shows only when a live run is scrolled up away from the newest entry
  const [atBottom, setAtBottom] = useState(true);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  function jumpToLatest() {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    pinned.current = true;
    setAtBottom(true);
  }

  return (
    <section
      aria-label="Orchestrator decision log"
      className={cn("relative flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-surface", className)}
    >
      {/* masthead — set, not labelled */}
      <header className="shrink-0 px-4 pt-3.5">
        <div className="flex items-end justify-between">
          <h2 className="display-soft text-[15px] leading-none text-foreground">
            Decision log
          </h2>
          <span className="flex items-center gap-1.5 text-[10px] text-faint">
            <span
              className={cn("size-1.5 rounded-full", live ? "animate-pulse-dot bg-primary" : "bg-faint")}
              aria-hidden
            />
            <span className="tabular tracking-wide">
              {live ? "LIVE" : "DONE"} · {entries.length}
            </span>
          </span>
        </div>
        <div className="mt-2.5 rule-strong" />
      </header>

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
          pinned.current = nearBottom;
          setAtBottom(nearBottom);
        }}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {entries.length === 0 ? (
          <p className="px-1 py-8 font-mono text-[12px] text-faint">
            Waiting for the pipeline to accept the brief
            <span className="caret" />
          </p>
        ) : (
          <ol className="divide-y divide-border/40">
            {entries.map((entry) => (
              <LogEntry key={entry.id} entry={entry} live={live} />
            ))}
            {live && (
              <li className="grid grid-cols-[2.9rem_1fr] sm:grid-cols-[3.6rem_1fr]">
                <span aria-hidden />
                <p className="border-l border-border/60 py-2 pl-4 font-mono text-[11.5px] text-faint">
                  orchestrating<span className="caret" />
                </p>
              </li>
            )}
          </ol>
        )}
      </div>

      {/* scrolled up while it's still streaming — one tap back to the newest line */}
      {live && !atBottom && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 cursor-pointer items-center gap-1.5 rounded-full border border-border-strong bg-surface-raised px-3 py-1.5 text-[11.5px] font-medium text-foreground shadow-md transition-colors hover:border-primary"
        >
          <ArrowDown className="size-3.5 text-primary" aria-hidden />
          Jump to live
        </button>
      )}
    </section>
  );
}
