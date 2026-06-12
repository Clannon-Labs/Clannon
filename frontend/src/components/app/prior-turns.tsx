"use client";

import { ChevronRight } from "lucide-react";
import type { Run } from "@/lib/api";
import { Report } from "@/components/app/report";

/**
 * The conversation so far: every turn of this session before the current one,
 * rendered as a compact thread (what you asked, what came back). The live turn
 * renders below this in full. Together they read as one continuing chat.
 */
export function PriorTurns({ turns }: { turns: Run[] }) {
  if (turns.length === 0) return null;

  return (
    <section aria-label="Earlier in this conversation" className="mb-8">
      <p className="tag-label text-faint">
        Earlier in this conversation · {turns.length}{" "}
        {turns.length === 1 ? "turn" : "turns"}
      </p>
      <ol className="mt-3 flex flex-col gap-3">
        {turns.map((turn, i) => (
          <li
            key={turn.id}
            className="overflow-hidden rounded-lg border border-border bg-surface"
          >
            {/* what the user asked */}
            <div className="flex items-start gap-3 border-b border-border px-4 py-3">
              <span className="tag-label mt-0.5 shrink-0 text-faint">{`0${i + 1}`}</span>
              <p className="text-sm leading-relaxed text-foreground">{turn.brief}</p>
            </div>
            {/* what came back — collapsed by default to keep the thread scannable */}
            {turn.report ? (
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
                  <ChevronRight
                    className="size-3.5 shrink-0 text-faint transition-transform duration-200 group-open:rotate-90"
                    aria-hidden
                  />
                  View the report from this turn
                </summary>
                <div className="border-t border-border px-4 py-4">
                  <Report markdown={turn.report} />
                </div>
              </details>
            ) : (
              <p className="px-4 py-2.5 text-[13px] text-faint">
                {turn.status === "blocked"
                  ? "No report — the output filter blocked this turn."
                  : turn.status === "failed"
                    ? "No report — this turn did not complete."
                    : "No report produced."}
              </p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
