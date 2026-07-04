"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ChevronRight, ListTree } from "lucide-react";
import { Mark } from "@/components/brand/logo";
import { DecisionLog } from "@/components/app/decision-log";
import { ExpertPanel, SourcesPanel } from "@/components/app/expert-panel";
import { EASE } from "@/components/motion";
import type { DecisionLogEntry, ExpertState, RunStatus, Source } from "@/lib/api";
import { cn } from "@/lib/utils";

/** A present-continuous verb for the live "working" indicator, derived from the
 *  newest decision-log entry (or the pipeline status before any logs arrive).
 *  Mirrors Claude/ChatGPT's collapsed "thinking" line. */
export function liveVerb(log: DecisionLogEntry[], status: RunStatus): string {
  const last = log[log.length - 1];
  if (last) {
    switch (last.kind) {
      case "hydration":
        return "Hydrating memory";
      case "route":
        return "Routing the work";
      case "expert_spawn":
        return "Calling experts";
      case "tool_call":
        return last.meta?.tool === "recall" || /\brecall\b/i.test(last.title)
          ? "Looking back at earlier"
          : "Calling a tool";
      case "observation":
        return "Reviewing findings";
      case "answer":
        return "Writing the report";
      case "warning":
      case "error":
        return last.title;
    }
  }
  switch (status) {
    case "queued":
      return "Queued";
    case "sanitizing":
      return "Scanning your input";
    case "verifying":
      return "Verifying";
    case "orchestrating":
      return "Orchestrating";
    case "filtering":
      return "Quality-checking";
    default:
      return "Working";
  }
}

/** m:ss elapsed since the run's first visible activity — the band's clock. */
function useElapsed(startTs: string | undefined, running: boolean): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);
  if (!startTs) return null;
  const s = Math.max(0, Math.floor((now - +new Date(startTs)) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const EXPERT_LIVE = new Set<ExpertState["status"]>(["spawned", "working", "summarizing"]);

/** The specialists, present DURING the stream — compact chips that slide into
 *  a rail as each expert spawns, so "parallel experts" is visible without
 *  expanding the work. The full ExpertPanel remains in the expanded view. */
function ExpertPresence({ experts, live }: { experts: ExpertState[]; live: boolean }) {
  const reduce = useReducedMotion();
  if (experts.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Experts on this run">
      {experts.map((expert) => {
        const working = live && EXPERT_LIVE.has(expert.status);
        return (
          <motion.li
            key={expert.id}
            initial={reduce ? false : { opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.24, ease: EASE }}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface py-1 pl-2 pr-2.5 font-mono text-[11px] text-muted-foreground"
          >
            <span
              className={cn(
                "size-1.5 rounded-full",
                expert.status === "failed" ? "bg-destructive" : "bg-log-expert",
                working && "animate-pulse-dot",
              )}
              aria-hidden
            />
            {expert.name}
            <span className="text-faint">/{expert.domain.toLowerCase()}</span>
          </motion.li>
        );
      })}
    </ul>
  );
}

/**
 * The agent's "work" — collapsed by default behind a single status band
 * (verb + caret + elapsed clock: one voice, not a pill/counter/verb trio),
 * with the experts present as chips even while collapsed. Expandable to the
 * full decision log and panels. Shared by the workspace run view AND the
 * no-signup demo so the two are identical and can't drift. `resetKey`
 * re-collapses it whenever the run changes.
 */
export function RunActivity({
  log,
  status,
  experts,
  sources,
  live,
  isTerminal,
  resetKey,
  className,
}: {
  log: DecisionLogEntry[];
  status: RunStatus;
  experts: ExpertState[];
  sources: Source[];
  live: boolean;
  isTerminal: boolean;
  resetKey: string;
  className?: string;
}) {
  const [showProcess, setShowProcess] = useState(false);
  const [decidedFor, setDecidedFor] = useState<string | null>(null);
  if (resetKey !== decidedFor) {
    setDecidedFor(resetKey);
    setShowProcess(false);
  }

  const elapsed = useElapsed(log[0]?.ts, live);
  // the settle moment — only when the terminal state arrives while watching
  const settled = isTerminal && live === false && log.length > 0
    ? status === "delivered"
      ? ("delivered" as const)
      : status === "blocked"
        ? ("blocked" as const)
        : null
    : null;

  return (
    <div className={className}>
      <div className="mt-4">
        {!isTerminal && !showProcess ? (
          <>
            {/* the one status voice: verb + caret + clock, expandable */}
            <button
              type="button"
              onClick={() => setShowProcess(true)}
              aria-expanded={false}
              aria-label="Show the agent's work"
              className="group inline-flex min-h-9 cursor-pointer items-center gap-2.5 text-[13px] transition-colors"
            >
              <Mark className="size-4 shrink-0 animate-pulse-dot text-primary" aria-hidden />
              <span className="font-medium text-foreground">
                {liveVerb(log, status)}
                {/* the caret ::after adds width — mr-1 keeps it off the interpunct */}
                <span className="caret mr-1" />
              </span>
              {elapsed && (
                <span className="font-mono text-[11px] text-faint tabular">{elapsed}</span>
              )}
              <span className="text-faint transition-colors group-hover:text-muted-foreground">
                · Show work
              </span>
              <ChevronRight
                className="size-3.5 shrink-0 text-faint transition-transform group-hover:translate-x-0.5"
                aria-hidden
              />
            </button>
            <ExpertPresence experts={experts} live={live} />
          </>
        ) : (
          <button
            type="button"
            onClick={() => setShowProcess((s) => !s)}
            aria-expanded={showProcess}
            className="inline-flex min-h-9 cursor-pointer items-center gap-2 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronRight
              className={cn(
                "size-3.5 shrink-0 text-faint transition-transform duration-200",
                showProcess && "rotate-90",
              )}
              aria-hidden
            />
            <ListTree className="size-3.5 shrink-0" aria-hidden />
            {showProcess ? "Hide work" : "Show work"}
            {!isTerminal && elapsed && (
              <span className="font-mono text-[11px] font-normal text-faint tabular">{elapsed}</span>
            )}
          </button>
        )}
      </div>

      {showProcess && (
        <div className="mt-3 flex flex-col gap-4">
          {/* hugs its content — grows with entries, scrolls past 60vh */}
          <DecisionLog entries={log} live={live} settled={settled} className="max-h-[60vh]" />
          <div className="grid gap-4 sm:grid-cols-2">
            <ExpertPanel experts={experts} />
            <SourcesPanel sources={sources} />
          </div>
        </div>
      )}
    </div>
  );
}
