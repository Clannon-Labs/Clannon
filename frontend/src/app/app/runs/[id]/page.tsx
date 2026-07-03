"use client";

import Link from "next/link";
import { use, useState } from "react";
import {
  ArrowLeft,
  ShieldAlert,
  Check,
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
import { useToast } from "@/components/ui/toast";
import { Tooltip, InfoTip } from "@/components/ui/tooltip";
import { useRun, useLiveRun, useRunThread, useDownloadArtifact, useCancelRun } from "@/lib/api/hooks";
import { Skeleton } from "@/components/ui/skeleton";
import { Report } from "@/components/app/report";
import { RunActivity } from "@/components/app/run-activity";
import { RunStatusBadge } from "@/components/app/run-status";
import { Reveal } from "@/components/motion";
import { RunComposer, ReportRating } from "@/components/app/run-feedback";
import { PriorTurns } from "@/components/app/prior-turns";
import { UserMessage } from "@/components/app/thread";
import { ArtifactPreview } from "@/components/app/artifact-preview";
import { Mark } from "@/components/brand/logo";
import type { Run, Artifact } from "@/lib/api";
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

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: run, isLoading, error } = useRun(id);
  const { data: thread } = useRunThread(id);
  const live = useLiveRun(run);
  const download = useDownloadArtifact();
  const cancel = useCancelRun(id);
  const toast = useToast();

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
      <div className="mt-3 flex flex-1 flex-col gap-6 pb-6">
        <PriorTurns turns={priorTurns} />

        {/* current turn — your ask, then Clannon's response */}
        <div className="flex flex-col items-end gap-1.5">
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
            <RunStatusBadge status={live.status} />
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
            <div
              role="alert"
              className="mt-5 flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive-soft p-4"
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
          />

          {/* report — the hero */}
          {showReport && (
            <section aria-label="Report" className="mt-6">
              <Reveal className="rounded-lg border border-border bg-surface">
                <header className="flex items-center justify-between border-b border-border px-5 py-3.5 sm:px-8">
                  <h2 className="tag-label text-muted-foreground">
                    {live.reportDone ? "Report — passed output filter" : "Report — streaming"}
                  </h2>
                  {live.reportDone && (
                    <span className="flex items-center gap-1">
                      <span className="tag-label mr-1 flex items-center gap-1.5 text-primary sm:mr-2">
                        <Check className="size-3.5" aria-hidden />
                        <span className="sr-only sm:not-sr-only">Verified</span>
                      </span>
                      <InfoTip
                        align="end"
                        label="Every claim was checked against its source before delivery. If it couldn't be grounded, it wouldn't ship."
                      />
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
      <div className="sticky bottom-0 z-30 border-t border-border bg-background/95 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 backdrop-blur-md">
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
