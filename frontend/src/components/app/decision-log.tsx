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

// `recall` is a tool_call the orchestrator uses to re-read an earlier turn of
// THIS session (a long chat gets condensed, so it looks things up instead of
// forgetting). We render it as the assistant consulting your shared history,
// not as plumbing — in the memory amber, so it reads as memory, not machinery.
const RECALL_META = { label: "RECALL", dot: "bg-log-memory", ink: "text-log-memory" };

function isRecall(entry: DecisionLogEntry): boolean {
  return (
    entry.kind === "tool_call" &&
    (entry.meta?.tool === "recall" || /\brecall\b/i.test(entry.title))
  );
}
function recallQuery(entry: DecisionLogEntry): string | null {
  return entry.meta?.query ?? entry.meta?.args ?? entry.detail ?? null;
}

/**
 * One transcript line. Set like a printed ledger: the timestamp lives in the
 * margin, a struck rule (the spine) runs down the gutter, and the kind tick
 * sits on the rule like a bullet. Each line prints itself once on mount —
 * which, on a live run, means every entry types in as it arrives.
 */
function LogEntry({
  entry,
  live,
  animate,
}: {
  entry: DecisionLogEntry;
  live: boolean;
  /** False for entries that were already there when the log mounted (or that
   *  a reconnect replays) — they render settled instead of re-typing. */
  animate: boolean;
}) {
  const reduce = useReducedMotion();
  const recall = isRecall(entry);
  const meta = recall ? RECALL_META : KIND_META[entry.kind];
  const flagged = entry.kind === "warning" || entry.kind === "error";
  // the payoff line — the draft landing gets the ignition treatment
  const major = entry.kind === "answer";
  const title = recall ? "Looking back at our earlier conversation" : entry.title;
  const query = recall ? recallQuery(entry) : null;

  return (
    <motion.li
      initial={reduce || !animate ? false : { opacity: 0, y: 7 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: EASE }}
      className={cn(
        "group grid grid-cols-[2.9rem_1fr] sm:grid-cols-[3.6rem_1fr]",
        major && !reduce && "animate-ignite rounded-sm",
      )}
    >
      {/* margin — the transcript's timestamp column */}
      <span className="select-none pr-2 pt-2 text-right text-[10px] leading-tight text-faint/80 tabular">
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
            // the heartbeat — a landing entry's tick swells once
            animate && "animate-tick-pulse",
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
            "mt-1 font-mono text-[13px] leading-snug text-foreground",
            major && "font-semibold",
          )}
        >
          {title}
        </p>
        {recall ? (
          query && (
            <p className="mt-1 font-mono text-[12px] italic leading-snug text-muted-foreground">
              “{query}”
            </p>
          )
        ) : (
          <>
            {entry.detail && (
              <p className="mt-1 font-mono text-[12px] leading-snug text-muted-foreground">
                {entry.detail}
              </p>
            )}
            {entry.meta && (
              <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
                {Object.entries(entry.meta).map(([k, v]) => (
                  <span key={k} className="font-mono text-[11px] text-faint">
                    {k}=<span className="text-muted-foreground">{v}</span>
                  </span>
                ))}
              </p>
            )}
          </>
        )}
      </div>
    </motion.li>
  );
}

export function DecisionLog({
  entries,
  live,
  settled,
  className,
}: {
  entries: DecisionLogEntry[];
  live: boolean;
  /** Terminal outcome, for the settle moment: the spine draws once in moss
   *  when a run delivers, in the destructive ink when it's blocked. */
  settled?: "delivered" | "blocked" | null;
  className?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  // whatever is already in the log when it mounts is history — it renders
  // settled, and only lines that arrive while watching print themselves.
  // (Opening a mid-flight run must not replay 30 entrances at once.)
  const [mountCount] = useState(() => entries.length);
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
          <span className="text-[10px] text-faint">
            <span className="tabular tracking-wide">{entries.length} entries</span>
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
        className="relative min-h-24 flex-1 overflow-y-auto px-4 py-2"
        aria-live="polite"
        aria-atomic="false"
      >
        {/* terminal settle — the spine ignites top-to-bottom once, then cools */}
        {settled && entries.length > 0 && (
          <span
            key={settled}
            aria-hidden
            className={cn(
              "pointer-events-none absolute bottom-2 left-[3.9rem] top-2 w-px origin-top animate-spine-ignite sm:left-[4.6rem]",
              settled === "delivered" ? "bg-primary" : "bg-destructive",
            )}
          />
        )}
        {entries.length === 0 ? (
          <p className="px-1 py-8 font-mono text-[12px] text-faint">
            Waiting for the pipeline to accept the brief
            <span className="caret" />
          </p>
        ) : (
          <ol className="divide-y divide-border/40">
            {entries.map((entry, i) => (
              <LogEntry key={entry.id} entry={entry} live={live} animate={i >= mountCount} />
            ))}
            {live && (
              <li className="grid grid-cols-[2.9rem_1fr] sm:grid-cols-[3.6rem_1fr]">
                <span aria-hidden />
                <p className="border-l border-border/60 py-2 pl-4 font-mono text-[12px] text-faint">
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
          className="absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 cursor-pointer items-center gap-1.5 rounded-full border border-border-strong bg-surface-raised px-3 py-1.5 text-[12px] font-medium text-foreground shadow-md transition-colors hover:border-primary"
        >
          <ArrowDown className="size-3.5 text-primary" aria-hidden />
          Jump to live
        </button>
      )}
    </section>
  );
}
