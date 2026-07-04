"use client";

import { useState } from "react";
import { ChevronRight, ListTree } from "lucide-react";
import { Mark } from "@/components/brand/logo";
import { DecisionLog } from "@/components/app/decision-log";
import { ExpertPanel, SourcesPanel } from "@/components/app/expert-panel";
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

/**
 * The agent's "work" — collapsed by default behind a live, animated verb line
 * (like Claude/ChatGPT thinking), expandable to the full decision log, the
 * experts, and the sources. Shared by the workspace run view AND the no-signup
 * demo so the two are identical and can't drift. `resetKey` re-collapses it
 * whenever the run changes (a new run id, or a fresh demo).
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
  // the activity (decision log, experts, sources) is COLLAPSED by default —
  // like Claude/ChatGPT thinking. While live it shows a compact animated
  // "working" line you can expand; once done it's a quiet "Show work" toggle.
  const [showProcess, setShowProcess] = useState(false);
  const [decidedFor, setDecidedFor] = useState<string | null>(null);
  if (resetKey !== decidedFor) {
    setDecidedFor(resetKey);
    setShowProcess(false);
  }

  return (
    <div className={className}>
      <div className="mt-4">
        {!isTerminal && !showProcess ? (
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
            <span className="text-faint transition-colors group-hover:text-muted-foreground">
              · Show work
            </span>
            <ChevronRight
              className="size-3.5 shrink-0 text-faint transition-transform group-hover:translate-x-0.5"
              aria-hidden
            />
          </button>
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
          </button>
        )}
      </div>

      {showProcess && (
        <div className="mt-3 flex flex-col gap-4">
          <DecisionLog entries={log} live={live} className="h-[360px]" />
          <div className="grid gap-4 sm:grid-cols-2">
            <ExpertPanel experts={experts} />
            <SourcesPanel sources={sources} />
          </div>
        </div>
      )}
    </div>
  );
}
