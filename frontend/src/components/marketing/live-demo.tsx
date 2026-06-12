"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { MockClient } from "@/lib/api/mock";
import type { DecisionLogEntry, RunStatus } from "@/lib/api";
import { DEMO_BRIEFS, DEMO_REPORT_PREVIEW_CHARS } from "@/config/demo.config";
import { ButtonLink } from "@/components/ui/button";
import { DecisionLog } from "@/components/app/decision-log";
import { Report } from "@/components/app/report";
import { RunStatusBadge } from "@/components/app/run-status";
import { SectionHeading } from "@/components/marketing/section-heading";
import { cn } from "@/lib/utils";

type Phase = "idle" | "running" | "done";

/**
 * The no-signup demo: picks a canned brief and plays the bundled
 * pipeline simulator inline. Deliberately constructs its own
 * MockClient — this section never talks to a real backend, matching
 * the isolated demo system in the architecture.
 */
export function LiveDemo() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [briefIndex, setBriefIndex] = useState(0);
  const [status, setStatus] = useState<RunStatus>("queued");
  const [log, setLog] = useState<DecisionLogEntry[]>([]);
  const [reportText, setReportText] = useState("");
  const [reportDone, setReportDone] = useState(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function start(index: number) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;

    setBriefIndex(index);
    setPhase("running");
    setStatus("queued");
    setLog([]);
    setReportText("");
    setReportDone(false);

    try {
      const client = new MockClient();
      const { id } = await client.createRun(DEMO_BRIEFS[index].brief);
      for await (const event of client.streamRun(id, abort.signal)) {
        if (event.type === "status") setStatus(event.status);
        else if (event.type === "log") setLog((l) => [...l, event.entry]);
        else if (event.type === "report_delta") setReportText((t) => t + event.text);
        else if (event.type === "report_done") setReportDone(true);
      }
      setPhase("done");
    } catch {
      // aborted (unmount or restart) — nothing to clean up
    }
  }

  const preview =
    reportText.length > DEMO_REPORT_PREVIEW_CHARS && reportDone
      ? reportText.slice(0, DEMO_REPORT_PREVIEW_CHARS).trimEnd() + "…"
      : reportText;

  return (
    <section id="demo" className="hairline-t">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:py-28">
        <SectionHeading
          kicker="Live demo — no signup"
          intro="Pick a brief and the pipeline runs right here — the same decision log, expert routing, and quality filter you get in the workspace."
        >
          Don&apos;t take our word for it. Watch a run.
        </SectionHeading>

        <div className="mt-8 flex flex-wrap gap-2">
          {DEMO_BRIEFS.map((demo, i) => (
            <button
              key={demo.label}
              type="button"
              disabled={phase === "running"}
              onClick={() => start(i)}
              className={cn(
                "cursor-pointer rounded-full border px-4 py-2 text-[13px] font-medium transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-50",
                phase !== "idle" && briefIndex === i
                  ? "border-primary bg-primary-soft text-primary"
                  : "border-border-strong text-muted-foreground hover:border-primary hover:text-foreground",
              )}
            >
              {demo.label}
            </button>
          ))}
          {phase === "done" && (
            <button
              type="button"
              onClick={() => start(briefIndex)}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-2 text-[13px] text-faint hover:text-foreground"
            >
              <RotateCcw className="size-3.5" aria-hidden /> Run again
            </button>
          )}
        </div>

        {phase !== "idle" && (
          <div className="dark mt-6 animate-fade-up rounded-xl border border-border bg-background p-1 text-foreground shadow-2xl shadow-black/25">
            <div className="rounded-[10px] bg-surface p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-muted-foreground">
                  {DEMO_BRIEFS[briefIndex].label}
                </p>
                <RunStatusBadge status={status} />
              </div>

              <DecisionLog
                entries={log}
                live={phase === "running" && !reportText}
                className="mt-4 h-[300px]"
              />

              {reportText && (
                <div className="mt-4 rounded-lg border border-border bg-background/60 px-5 py-5 sm:px-7">
                  <Report markdown={preview} streaming={!reportDone} ornate={reportDone} />
                  {reportDone && (
                    <div className="mt-5 border-t border-border pt-5 text-center">
                      <p className="text-sm text-muted-foreground">
                        The full report continues — with every source linked.
                      </p>
                      <ButtonLink href="/signup" className="mt-4">
                        Run your own brief, free
                        <ArrowRight className="size-4" aria-hidden />
                      </ButtonLink>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
