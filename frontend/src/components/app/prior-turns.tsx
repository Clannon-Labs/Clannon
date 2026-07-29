"use client";

import { ChevronRight } from "lucide-react";
import type { Run } from "@/lib/api";
import { Report } from "@/components/app/report";
import { AssistantMessage } from "@/components/app/thread";
import { TurnPrompt } from "@/components/app/turn-prompt";

type RevisePrompt = (runId: string, brief: string) => Promise<void>;

/** Copy for a turn that produced no report, by how it ended. */
function noReportNote(status: Run["status"]): string {
  switch (status) {
    case "blocked":
      return "No report — the output filter blocked this turn.";
    case "failed":
      return "No report — this turn did not complete.";
    case "cancelled":
      return "No report — you stopped this turn.";
    default:
      return "No report produced.";
  }
}

/**
 * The conversation so far: every turn of this session before the current one,
 * rendered as a chat thread (your ask, then what came back). The live turn
 * renders below this in full. Together they read as one continuing conversation.
 */
export function PriorTurns({
  turns,
  onRevise,
}: {
  turns: Run[];
  onRevise?: RevisePrompt;
}) {
  if (turns.length === 0) return null;

  return (
    <section aria-label="Earlier in this conversation" className="mb-8 flex flex-col gap-6">
      {turns.map((turn, index) => (
        <div key={turn.id} className="flex flex-col gap-3">
          <TurnPrompt
            turn={turn}
            laterTurnCount={turns.length - index}
            onRevise={onRevise}
          />
          <AssistantMessage>
            {/* the agent's conversational note (commentary) */}
            {turn.message && (
              <div className={turn.report ? "mb-3" : undefined}>
                <Report markdown={turn.message} />
              </div>
            )}
            {/* the deliverable — collapsed by default to keep the thread scannable */}
            {turn.report ? (
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
                  <ChevronRight
                    className="size-3.5 shrink-0 text-faint transition-transform duration-200 group-open:rotate-90"
                    aria-hidden
                  />
                  View the report from this turn
                </summary>
                <div className="mt-3 border-t border-border pt-4">
                  <Report markdown={turn.report} />
                </div>
              </details>
            ) : !turn.message ? (
              <p className="text-[13px] text-faint">{noReportNote(turn.status)}</p>
            ) : null}
          </AssistantMessage>
        </div>
      ))}
    </section>
  );
}
