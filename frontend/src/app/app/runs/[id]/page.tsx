"use client";

import Link from "next/link";
import { use, useState } from "react";
import { ArrowLeft, ShieldAlert, Check, Copy, Download, ChevronRight, ListTree } from "lucide-react";
import { useToast } from "@/components/ui/toast";
import { useRun, useLiveRun, useRunThread } from "@/lib/api/hooks";
import { Skeleton } from "@/components/ui/skeleton";
import { DecisionLog } from "@/components/app/decision-log";
import { ExpertPanel, SourcesPanel } from "@/components/app/expert-panel";
import { Report } from "@/components/app/report";
import {
  RunStatusBadge,
  PIPELINE_STAGES,
  stageIndex,
} from "@/components/app/run-status";
import { Reveal, Rule } from "@/components/motion";
import { RunFeedback } from "@/components/app/run-feedback";
import { PriorTurns } from "@/components/app/prior-turns";
import type { Run } from "@/lib/api";
import { cn, formatTokens } from "@/lib/utils";

/** An honest, stage-specific block message — not the old "verifier found PII"
 *  catch-all, which was wrong for output-filter blocks. */
function blockMessage(stage: Run["blockStage"]): { title: string; body: string } {
  switch (stage) {
    case "sanitize":
      return {
        title: "Blocked before processing",
        body: "The input scanner flagged the brief (malware signature, or unsafe/malformed content) and stopped it. Nothing was sent to the models. Edit the brief and resubmit.",
      };
    case "verify":
      return {
        title: "Blocked by the verifier",
        body: "The verifier found content it couldn't safely process in the brief (for example, unredacted personal data). Nothing was sent to the models. Edit the brief and resubmit.",
      };
    case "filter":
      return {
        title: "Held back by the output filter",
        body: "A draft was produced but the output filter didn't clear it for delivery. This can happen if claims couldn't be grounded in the research. Try rephrasing, or run it again.",
      };
    default:
      return {
        title: "Run blocked by the security pipeline",
        body: "A security gate stopped this run before delivery. Your token budget was not charged for blocked work.",
      };
  }
}

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: run, isLoading, error } = useRun(id);
  const { data: thread } = useRunThread(id);
  const live = useLiveRun(run);
  const toast = useToast();

  // turns of this session that came before the one on screen — the chat history.
  // thread is oldest-first; take everything up to the current turn.
  const orderedThread = thread ?? [];
  const currentIndex = orderedThread.findIndex((t) => t.id === id);
  const priorTurns = currentIndex > 0 ? orderedThread.slice(0, currentIndex) : [];

  // the input + decision log collapse together — one toggle for "the process",
  // so a finished turn reads as a clean report with the composer below
  const [showProcess, setShowProcess] = useState(true);

  async function copyReport() {
    await navigator.clipboard.writeText(live.reportText);
    toast({ title: "Report copied as markdown", tone: "success" });
  }

  function downloadReport() {
    const blob = new Blob([live.reportText], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(run?.title ?? "report").replace(/[^\w-]+/g, "-").slice(0, 60)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-[60vh]" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="mx-auto max-w-2xl py-20 text-center">
        <h1 className="display text-[2rem]">Run not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          It may have been removed, or the link is wrong.
        </p>
        <Link
          href="/app"
          className="mt-6 inline-flex items-center gap-2 text-sm text-primary underline-offset-4 hover:underline"
        >
          <ArrowLeft className="size-4" aria-hidden /> Back to workspace
        </Link>
      </div>
    );
  }

  const currentStage = stageIndex(live.status);
  const isTerminalFailure = live.status === "blocked" || live.status === "failed";
  const showReport = live.reportText.length > 0;

  return (
    <div className="mx-auto max-w-6xl">
      <Link
        href="/app"
        className="inline-flex items-center gap-1.5 py-2 text-[13px] text-faint transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden /> Workspace
      </Link>

      {/* the conversation so far — prior turns of this session */}
      <div className="mt-4">
        <PriorTurns turns={priorTurns} />
      </div>

      {/* current turn */}
      <header>
        {priorTurns.length > 0 && (
          <p className="tag-label mb-2 text-primary">This turn</p>
        )}
        <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
          <h1 className="display min-w-0 flex-1 basis-full text-balance text-[2rem] leading-[1.02] sm:basis-auto sm:text-[2.6rem]">
            {run.title}
          </h1>
          <div className="flex items-center gap-3 pt-1">
            <RunStatusBadge status={live.status} />
            {live.tokensUsed > 0 && (
              <span className="text-[12.5px] text-faint tabular">
                {formatTokens(live.tokensUsed)} tokens
              </span>
            )}
          </div>
        </div>
        <Rule className="mt-5" />
      </header>

      {/* one control for "the process" — your input AND the decision log collapse
          together, so a finished turn reads as a clean report + composer */}
      <div className="mt-5 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setShowProcess((s) => !s)}
          aria-expanded={showProcess}
          className="inline-flex min-h-9 cursor-pointer items-center gap-2 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronRight
            className={cn("size-3.5 shrink-0 text-faint transition-transform duration-200", showProcess && "rotate-90")}
            aria-hidden
          />
          <ListTree className="size-3.5 shrink-0" aria-hidden />
          {showProcess ? "Hide input & decision log" : "Show input & decision log"}
        </button>
      </div>

      {/* the brief — the title is a truncated preview; this is the full input */}
      {showProcess && run.brief && (
        <p className="mt-3 whitespace-pre-wrap rounded-lg border border-border bg-surface px-4 py-3.5 text-sm leading-relaxed text-foreground">
          {run.brief}
        </p>
      )}

      {/* pipeline progress — a ruled strike across the stages, not a row of pills */}
      <ol className="hairline-b mt-6 flex items-stretch overflow-x-auto" aria-label="Pipeline stages">
        {PIPELINE_STAGES.map((stage, i) => {
          const done = currentStage > i || live.status === "delivered";
          const active = currentStage === i && !isTerminalFailure && live.status !== "delivered";
          return (
            <li
              key={stage.key}
              className="relative flex shrink-0 items-center gap-2 px-4 py-2.5 first:pl-1"
            >
              <span
                className={cn(
                  "font-mono text-[10px] tabular",
                  done || active ? "text-primary" : "text-faint",
                )}
              >
                0{i + 1}
              </span>
              <span
                className={cn(
                  "font-mono text-[11px] uppercase tracking-[0.14em]",
                  done ? "text-foreground" : active ? "text-primary" : "text-faint",
                )}
              >
                {stage.label}
              </span>
              {done && <Check className="size-3 text-primary" aria-hidden />}
              {active && (
                <span className="size-1.5 animate-pulse-dot rounded-full bg-primary" aria-hidden />
              )}
              {/* the strike — completed and live stages carry the rule */}
              {(done || active) && (
                <span
                  className={cn(
                    "absolute inset-x-0 bottom-0 h-[2px]",
                    done ? "bg-primary" : "bg-primary/60",
                  )}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>

      {isTerminalFailure && (
        <div
          role="alert"
          className="mt-6 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive-soft p-4"
        >
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
          <div>
            <p className="text-sm font-semibold text-destructive">
              {live.status === "blocked" ? blockMessage(run.blockStage).title : "Run failed"}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {live.status === "blocked"
                ? blockMessage(run.blockStage).body
                : "A pipeline stage failed before delivery. Your token budget was not charged for incomplete work."}
            </p>
          </div>
        </div>
      )}

      {live.streamError && (
        <p role="alert" className="mt-4 rounded-md border border-warning/40 bg-memory-soft px-4 py-3 text-sm text-memory">
          {live.streamError}
        </p>
      )}

      {/* live grid — collapses with the input under the one toggle above */}
      {showProcess && (
        <div className="mt-6 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <DecisionLog
            entries={live.log}
            live={live.live}
            className="h-[420px] lg:h-[480px]"
          />
          <div className="flex flex-col gap-4">
            <ExpertPanel experts={live.experts} />
            <SourcesPanel sources={live.sources} />
          </div>
        </div>
      )}

      {/* report */}
      {showReport && (
        <section aria-label="Report" className="mt-8">
          <Reveal className="rounded-lg border border-border bg-surface">
            <header className="flex items-center justify-between border-b border-border px-5 py-3.5 sm:px-8">
              <h2 className="tag-label text-muted-foreground">
                {live.reportDone ? "Report — passed output filter" : "Report — streaming"}
              </h2>
              {live.reportDone && (
                <span className="flex items-center gap-1">
                  <span className="tag-label mr-2 hidden items-center gap-1.5 text-primary sm:flex">
                    <Check className="size-3.5" aria-hidden /> Verified
                  </span>
                  <button
                    type="button"
                    onClick={copyReport}
                    aria-label="Copy report as markdown"
                    title="Copy markdown"
                    className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Copy className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={downloadReport}
                    aria-label="Download report as a markdown file"
                    title="Download .md"
                    className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Download className="size-4" />
                  </button>
                </span>
              )}
            </header>
            <div className="px-5 py-6 sm:px-8 sm:py-8">
              <Report
                markdown={live.reportText}
                streaming={!live.reportDone}
                ornate={live.reportDone}
              />
            </div>
          </Reveal>
        </section>
      )}

      {/* continue the conversation — available on ANY terminal turn, including a
          blocked or failed one, so a block is never a dead end. The thumbs
          rating only shows when there's a delivered report to rate. */}
      {(live.reportDone || isTerminalFailure) && (
        <RunFeedback
          runId={run.id}
          initialRating={run.feedbackRating}
          canRate={live.reportDone}
        />
      )}
    </div>
  );
}
