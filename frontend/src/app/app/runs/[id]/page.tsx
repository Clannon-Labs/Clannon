"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ShieldAlert,
  Clock,
  Copy,
  Download,
  Square,
  File,
  FileText,
  FileType,
  FileAudio,
  FileVideo,
  Image,
  type LucideIcon,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { useRun, useLiveRun, useRunThread, useDownloadArtifact, useCancelRun } from "@/lib/api/hooks";
import { Skeleton } from "@/components/ui/skeleton";
import { Report } from "@/components/app/report";
import { RunActivity } from "@/components/app/run-activity";
import { RunStatusBadge } from "@/components/app/run-status";
import { EASE, Reveal } from "@/components/motion";
import { RunComposer, ReportRating } from "@/components/app/run-feedback";
import { PriorTurns } from "@/components/app/prior-turns";
import { UserMessage } from "@/components/app/thread";
import { ArtifactPreview } from "@/components/app/artifact-preview";
import { Mark } from "@/components/brand/logo";
import { VerificationStatus } from "@/components/app/verification-status";
import type { Run, Artifact, CompletionReason } from "@/lib/api";
import { formatBytes, formatTokens } from "@/lib/utils";

/** Icon for an attached input file, picked by modality (text/pdf today;
 *  image/audio/video slot in as the backend's media support lands). */
function iconForModality(modality: string): LucideIcon {
  switch (modality) {
    case "pdf":
      return FileType;
    case "image":
      return Image;
    case "audio":
      return FileAudio;
    case "video":
      return FileVideo;
    case "text":
      return FileText;
    default:
      return File;
  }
}

/** Icon for a delivered artifact, picked by its mime type. */
function iconForMime(mime: string): LucideIcon {
  if (mime.startsWith("image/")) return Image;
  if (mime.startsWith("audio/")) return FileAudio;
  if (mime.startsWith("video/")) return FileVideo;
  if (mime === "application/pdf") return FileType;
  if (mime.startsWith("text/")) return FileText;
  return File;
}

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

/** Why the loop stopped short of finishing — distinct from `verificationState`
 *  (whether the claims it DID make are grounded) and `status` (how it ended).
 *  A partial run is routinely delivered and grounded at once. */
function completionMessage(reason: CompletionReason): { title: string; body: string } {
  switch (reason) {
    case "timeout":
      return {
        title: "Ran out of time before finishing",
        body: "It hit the per-run time budget before covering everything the brief asked for. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    case "rate_limit":
      return {
        title: "Interrupted by a rate limit",
        body: "An upstream rate limit stopped it before it finished everything planned. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    case "error":
      return {
        title: "Interrupted by an error",
        body: "Something failed mid-run before it finished everything planned. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    default:
      return {
        title: "Didn't finish everything planned",
        body: "The loop stopped before covering the full brief. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
  }
}

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: run, isLoading, error } = useRun(id);
  const { data: thread } = useRunThread(id);
  const live = useLiveRun(run);
  const download = useDownloadArtifact();
  const cancel = useCancelRun(id);
  const toast = useToast();
  const reduce = useReducedMotion();

  // when delivery happens WHILE watching, bring the payoff into view — on a
  // phone the report otherwise lands below the fold behind the composer.
  // (No scroll when opening an already-delivered run: prev starts null.)
  const reportRef = useRef<HTMLElement>(null);
  const prevReportDone = useRef<boolean | null>(null);
  useEffect(() => {
    const was = prevReportDone.current;
    prevReportDone.current = live.reportDone;
    if (was === false && live.reportDone) {
      reportRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }
  }, [live.reportDone, reduce]);

  // turns of this session that came before the one on screen — the chat history.
  // thread is oldest-first; take everything up to the current turn.
  const orderedThread = thread ?? [];
  const currentIndex = orderedThread.findIndex((t) => t.id === id);
  const priorTurns = currentIndex > 0 ? orderedThread.slice(0, currentIndex) : [];

  // the artifact being previewed inline (click a file to open it in the chat)
  const [preview, setPreview] = useState<Artifact | null>(null);

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

  function saveArtifact(name: string) {
    if (!run) return;
    download.mutate(
      { runId: run.id, name },
      {
        onSuccess: (blob) => {
          const objectUrl = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = objectUrl;
          a.download = name;
          a.click();
          URL.revokeObjectURL(objectUrl);
        },
        onError: () => toast({ title: `Couldn't download ${name}`, tone: "warning" }),
      },
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
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

  const isFailure = live.status === "blocked" || live.status === "failed";
  const isCancelled = live.status === "cancelled";
  const isTerminal = live.status === "delivered" || isFailure || isCancelled;
  // completionState is a THIRD axis, never derived from status or
  // verificationState (INTEGRATION_CONTRACT.md) — a delivered, grounded run
  // can still be partial. Only meaningful once the run has actually delivered.
  const isPartial = live.status === "delivered" && run.completionState === "partial";
  const showReport = live.reportText.length > 0;

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-7rem)] max-w-3xl flex-col md:min-h-[calc(100dvh-4rem)]">
      <Link
        href="/app"
        className="inline-flex items-center gap-1.5 py-2 text-[13px] text-faint transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden /> Workspace
      </Link>
      <h1 className="sr-only">{run.title}</h1>

      {/* the conversation — prior turns, then the current turn, as one thread */}
      <div className="mt-3 flex flex-1 flex-col gap-6 pb-10">
        <PriorTurns turns={priorTurns} />

        {/* current turn — your ask, then Clannon's response. The brief bubble
            carries the shared view-transition-name, so the clicked run row in
            the rail MORPHS into it on navigation (the run opening from the
            list into the page). Keyed per run id; paired with the row. */}
        <div
          className="flex flex-col items-end gap-1.5"
          style={{ viewTransitionName: `run-open-${id.replace(/[^a-zA-Z0-9]/g, "-")}` }}
        >
          <UserMessage>{run.brief}</UserMessage>
          {run.inputs && run.inputs.length > 0 && (
            <ul className="flex max-w-[85%] flex-wrap justify-end gap-2" aria-label="Attached files">
              {run.inputs.map((input, i) => {
                const Icon = iconForModality(input.modality);
                return (
                  <li
                    key={`${input.name}-${i}`}
                    className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] text-muted-foreground"
                  >
                    <Icon className="size-3.5 shrink-0 text-faint" aria-hidden />
                    <span className="truncate">{input.name}</span>
                    <span className="shrink-0 text-faint tabular">{formatBytes(input.size)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* the assistant turn — full width so the report reads as the result */}
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="flex items-center gap-2">
              <Mark className="size-5 text-primary" aria-hidden />
              <span className="font-display text-[15px] font-medium">Clannon</span>
            </span>
            {/* the band below owns the live voice; the pill returns for the
                terminal verdict */}
            {isTerminal && <RunStatusBadge status={live.status} />}
            {isPartial && (
              <span className="tag-label inline-flex items-center gap-1.5 rounded-full bg-memory-soft px-2.5 py-1 text-memory">
                <Clock className="size-3.5" aria-hidden />
                Partial
              </span>
            )}
            {live.tokensUsed > 0 && (
              <span className="text-[12px] text-faint tabular">
                {formatTokens(live.tokensUsed)} tokens
              </span>
            )}
          </div>

          {/* the agent talking — conversational commentary, streamed live (even
              while experts work). NOT the deliverable, NOT output-filtered. */}
          {live.message && (
            <div className="mt-3">
              <Report markdown={live.message} streaming={live.live && !live.messageDone} />
            </div>
          )}

          {isFailure && (
            /* set in the ledger's own language — a struck rule, a kicker, and
               ONE way forward — instead of an alert box shouting */
            <div role="alert" className="mt-5 border-l-2 border-destructive pl-4">
              <p className="tag-label flex items-center gap-1.5 text-destructive">
                <ShieldAlert className="size-3.5" aria-hidden />
                {/* the status pill above already says BLOCKED — the kicker
                    names the gate, it doesn't repeat the verdict */}
                {live.status === "blocked"
                  ? `${run.blockStage ?? "security"} gate`
                  : "Run failed"}
              </p>
              <p className="mt-1.5 text-sm font-medium text-foreground">
                {live.status === "blocked" ? blockMessage(run.blockStage).title : "Run failed"}
              </p>
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">
                {live.status === "blocked"
                  ? blockMessage(run.blockStage).body
                  : "A pipeline stage failed before delivery. Your token budget was not charged for incomplete work."}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => document.getElementById("composer-input")?.focus()}
              >
                Edit and resubmit
              </Button>
            </div>
          )}

          {/* user-stopped — neutral, not an error; the composer below continues it */}
          {isCancelled && (
            <div
              role="status"
              className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-surface p-4"
            >
              <Square className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />
              <div>
                <p className="text-sm font-semibold text-foreground">You stopped this run</p>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  It stopped before delivering a report. Anything it had already done
                  is kept. Pick up where you left off below, or start a fresh turn.
                </p>
              </div>
            </div>
          )}

          {/* incomplete but real — not an error, not a re-run of what already
              shipped. Reads its cause instead of forcing you into the report
              to guess why it feels short. */}
          {isPartial && (
            <div
              role="status"
              className="mt-5 border-l-2 border-warning/40 pl-4"
            >
              <p className="tag-label flex items-center gap-1.5 text-memory">
                <Clock className="size-3.5" aria-hidden />
                {completionMessage(run.completionReason ?? null).title}
              </p>
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">
                {completionMessage(run.completionReason ?? null).body}
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => document.getElementById("composer-input")?.focus()}
              >
                Continue this run
              </Button>
            </div>
          )}

          {live.reconnecting && (
            <p
              role="status"
              className="mt-4 flex items-center gap-2 rounded-md border border-warning/40 bg-memory-soft px-4 py-3 text-sm text-memory"
            >
              <span className="size-1.5 animate-pulse-dot rounded-full bg-memory" aria-hidden />
              Connection lost — reconnecting…
            </p>
          )}

          {live.streamError && (
            <p role="alert" className="mt-4 rounded-md border border-warning/40 bg-memory-soft px-4 py-3 text-sm text-memory">
              {live.streamError}
            </p>
          )}

          {/* the agent's work — collapsed by default behind a live verb line.
              Shared with the no-signup demo so the two are pixel-identical. */}
          <RunActivity
            log={live.log}
            status={live.status}
            experts={live.experts}
            sources={live.sources}
            live={live.live}
            isTerminal={isTerminal}
            resetKey={run.id}
            runId={run.id}
          />

          {/* report — the hero */}
          {showReport && (
            <section ref={reportRef} aria-label="Report" className="mt-6 scroll-mt-4">
              {/* the payoff frame — a lit SHEET on the dark desk: narrower than
                  the thread so the desk shows around it (a page of paper, not a
                  full-bleed panel), with its own warm-cast surface, edge-light,
                  and a real shadow. The measure fills the sheet — no dead gutter. */}
              <Reveal className="mx-auto max-w-[40rem] rounded-lg border border-border-strong bg-sheet [box-shadow:inset_0_1px_0_0_rgb(255_255_255/0.9),0_16px_38px_-14px_rgb(45_38_18/0.3)] dark:[box-shadow:inset_0_1px_0_0_var(--edge-light),0_18px_44px_-16px_rgb(0_0_0/0.7)]">
                <header className="sticky top-0 z-10 flex items-center justify-between rounded-t-lg border-b border-border bg-sheet/95 px-5 py-3.5 backdrop-blur-md sm:px-8">
                  {/* a tag-label never wraps — below sm the gate suffix goes, not the line */}
                  <h2 className="tag-label text-muted-foreground">
                    Report
                    <span className="hidden sm:inline">
                      {live.reportDone ? " — passed output filter" : " — streaming"}
                    </span>
                  </h2>
                  {/* the filter passing is the payoff — a moss rule strikes
                      across the masthead as the verified mark rises in */}
                  {live.reportDone && !reduce && (
                    <motion.span
                      aria-hidden
                      className="absolute inset-x-0 bottom-[-1px] h-px origin-left bg-primary/50"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ duration: 0.55, ease: EASE, delay: 0.1 }}
                    />
                  )}
                  {live.reportDone && (
                    <motion.span
                      initial={reduce ? false : { opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.25, ease: EASE }}
                      className="flex items-center gap-1"
                    >
                      <VerificationStatus state={live.verificationState} />
                      <Tooltip label="Copy markdown" align="end">
                        <button
                          type="button"
                          onClick={copyReport}
                          aria-label="Copy report as markdown"
                          className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
                        >
                          <Copy className="size-4" />
                        </button>
                      </Tooltip>
                      <Tooltip label="Download .md" align="end">
                        <button
                          type="button"
                          onClick={downloadReport}
                          aria-label="Download report as a markdown file"
                          className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
                        >
                          <Download className="size-4" />
                        </button>
                      </Tooltip>
                    </motion.span>
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

          {/* files this run delivered — the canonical download UI */}
          {run.artifacts && run.artifacts.length > 0 && (
            <section aria-label="Files" className="mt-6">
              <h2 className="tag-label text-faint">Files</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {run.artifacts.map((artifact) => {
                  const Icon = iconForMime(artifact.mime);
                  return (
                    <li
                      key={artifact.id}
                      className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface p-1.5 pr-2"
                    >
                      {/* click the file to preview it inline — no download needed */}
                      <button
                        type="button"
                        onClick={() => setPreview(artifact)}
                        title={`Preview ${artifact.name}`}
                        className="flex min-w-0 flex-1 items-center gap-3 rounded-md px-2.5 py-1.5 text-left transition-colors hover:bg-muted"
                      >
                        <Icon className="size-4 shrink-0 text-faint" aria-hidden />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {artifact.name}
                          </p>
                          <p className="text-[12px] text-faint tabular">
                            {artifact.mime} · {formatBytes(artifact.size)} · Click to preview
                          </p>
                        </div>
                      </button>
                      <Tooltip label="Download" align="end">
                        <button
                          type="button"
                          onClick={() => saveArtifact(artifact.name)}
                          aria-label={`Download ${artifact.name}`}
                          className="flex size-9 shrink-0 items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
                        >
                          <Download className="size-4" aria-hidden />
                        </button>
                      </Tooltip>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {/* per-report rating — only when there's a delivered report to rate */}
          {live.reportDone && (
            <ReportRating runId={run.id} initialRating={run.feedbackRating} />
          )}
        </div>
      </div>

      {/* docked composer — ALWAYS visible, like every chat app. While the run is
          in flight the send button becomes Stop and you can type your next
          message; on mobile the bottom nav steps aside (see Sidebar). */}
      <div className="composer-scrim sticky bottom-0 z-30 border-t border-border bg-background pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3">
        <RunComposer
          runId={run.id}
          busy={!isTerminal}
          onStop={() => cancel.mutate()}
        />
      </div>

      {preview && (
        <ArtifactPreview
          runId={run.id}
          artifact={preview}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
