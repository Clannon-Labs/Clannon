"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowRight, MessagesSquare, Paperclip, Sprout } from "lucide-react";
import { useCreateRun, useMe, useRuns } from "@/lib/api/hooks";
import { ApiError, type RunSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import { RunStatusBadge } from "@/components/app/run-status";
import { HydrationPanel } from "@/components/app/hydration-panel";
import {
  useFileAttachments,
  AttachmentChips,
  DropOverlay,
  HeavyMediaNote,
} from "@/components/app/attachments";
import { ACCEPTED_INPUT } from "@/lib/uploads";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";

import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";
import { appConfig } from "@/config/app.config";

interface SessionEntry {
  sessionId: string;
  title: string;          // the original ask — the session's topic
  latestId: string;       // newest turn; the link target (renders the full thread)
  status: RunSummary["status"];
  createdAt: string;      // latest activity
  turnCount: number;
  tokensUsed: number;
  expertCount: number;
}

/** Group runs into sessions: turns sharing a sessionId become one entry. */
function groupBySession(runs: RunSummary[] | undefined): SessionEntry[] {
  if (!runs) return [];
  const groups = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const sid = run.sessionId ?? run.id;
    const bucket = groups.get(sid);
    if (bucket) bucket.push(run);
    else groups.set(sid, [run]);
  }
  return [...groups.values()]
    .map((turns) => {
      const ordered = [...turns].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
      const first = ordered[0];
      const latest = ordered[ordered.length - 1];
      return {
        sessionId: first.sessionId ?? first.id,
        title: first.title,
        latestId: latest.id,
        status: latest.status,
        createdAt: latest.createdAt,
        turnCount: ordered.length,
        tokensUsed: ordered.reduce((sum, t) => sum + t.tokensUsed, 0),
        expertCount: ordered.reduce((sum, t) => sum + t.expertCount, 0),
      };
    })
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export default function WorkspacePage() {
  const router = useRouter();
  const { data: user } = useMe();
  const { data: runs, isLoading } = useRuns();
  const createRun = useCreateRun();
  const [brief, setBrief] = useState("");
  const [error, setError] = useState<string | null>(null);
  const attach = useFileAttachments();
  const fileRef = useRef<HTMLInputElement>(null);

  const firstName = user?.name.split(" ")[0] ?? "";
  const tooShort = brief.trim().length < appConfig.limits.briefMinChars;

  // collapse a multi-turn conversation into ONE entry: a session shows the
  // original ask as its title, links to the latest turn (which renders the full
  // thread), and aggregates turn count + tokens.
  const sessions = useMemo(() => groupBySession(runs), [runs]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createRun.mutate(
      { brief, files: attach.files },
      {
        onSuccess: ({ id }) => router.push(`/app/runs/${id}`),
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Could not start the run — try again."),
      },
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <header>
        <p className="tag-label text-faint">Workspace</p>
        <h1 className="display mt-3 text-[2.4rem] leading-[1.0] sm:text-[3rem]">
          What can I help with
          {firstName ? (
            <>
              , <span className="capitalize text-primary">{firstName}</span>?
            </>
          ) : (
            "?"
          )}
        </h1>
      </header>

      {/* brief composer */}
      <form onSubmit={onSubmit} className="mt-8">
        <div
          {...attach.dropZoneProps}
          className={cn(
            "relative overflow-hidden rounded-lg border border-border-strong bg-surface transition-colors focus-within:border-primary",
            attach.dragOver && "border-primary ring-2 ring-primary/30",
          )}
        >
          <DropOverlay show={attach.dragOver} />
          <label htmlFor="brief" className="sr-only">
            Message
          </label>
          <textarea
            id="brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift/Cmd/Ctrl+Enter insert a newline. Never submit
              // mid IME composition (non-Latin input), when empty, or in flight.
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.metaKey &&
                !e.ctrlKey &&
                !e.altKey &&
                !e.nativeEvent.isComposing &&
                !tooShort &&
                !createRun.isPending
              ) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Ask anything — a quick question, or a whole brief to dig into…"
            rows={5}
            className="w-full resize-none bg-transparent px-5 py-4 text-base leading-relaxed placeholder:text-faint focus:outline-none sm:text-[15px]"
          />
          <AttachmentChips files={attach.files} onRemove={attach.removeFile} />
          <HeavyMediaNote show={attach.hasHeavyMedia} />
          <div className="flex flex-col gap-3 border-t border-border bg-background/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-md text-[12.5px] font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                <Paperclip className="size-4" aria-hidden /> Attach
              </button>
              <input
                ref={fileRef}
                type="file"
                accept={ACCEPTED_INPUT}
                multiple
                className="hidden"
                aria-label="Attach input files — text files, PDFs, images, audio, or video"
                onChange={attach.handlePicked}
              />
              <p className="text-[12px] text-faint" aria-live="polite">
                {tooShort ? (
                  <span className="text-muted-foreground">
                    {brief.trim().length === 0
                      ? "Type a message to begin."
                      : "Say a little more…"}
                  </span>
                ) : (
                  <>
                    <kbd className="rounded border border-border px-1 font-mono text-[11px]">↵</kbd> to send ·{" "}
                    <kbd className="rounded border border-border px-1 font-mono text-[11px]">⇧↵</kbd> new line
                  </>
                )}
              </p>
            </div>
            <Button
              type="submit"
              loading={createRun.isPending}
              disabled={tooShort}
            >
              {createRun.isPending ? "Sending…" : "Send"}
              {!createRun.isPending && <ArrowRight className="size-4" aria-hidden />}
            </Button>
          </div>
        </div>
        {(error || attach.error) && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {error || attach.error}
          </p>
        )}
      </form>

      {/* example briefs */}
      <div className="mt-4 flex flex-wrap gap-2">
        {EXAMPLE_BRIEFS.map((example) => (
          <button
            key={example.slice(0, 24)}
            type="button"
            onClick={() => setBrief(example)}
            className="min-h-10 cursor-pointer rounded-full border border-border bg-surface px-3.5 py-1.5 text-left text-[12.5px] text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
          >
            {example.split(":")[0].split(".")[0]}
          </button>
        ))}
      </div>

      {/* the hydration moment — context surfaces before the brief is even sent */}
      <HydrationPanel brief={brief} className="mt-8" />

      {/* recent sessions — a multi-turn conversation collapses into one entry */}
      <section className="mt-14" aria-label="Recent sessions">
        <div className="flex items-baseline justify-between">
          <h2 className="tag-label text-faint">Recent sessions</h2>
        </div>

        {isLoading ? (
          <div className="mt-4 flex flex-col gap-2">
            <Skeleton className="h-[72px]" />
            <Skeleton className="h-[72px]" />
            <Skeleton className="h-[72px]" />
          </div>
        ) : sessions.length === 0 ? (
          <EmptyState
            className="mt-4"
            icon={<Sprout className="size-8" aria-hidden />}
            title="Nothing planted yet"
            description="Run your first brief above. Every run becomes a ring in your archive — searchable, citable, remembered."
          />
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
            {sessions.map((session) => (
              <li key={session.sessionId}>
                <Link
                  href={`/app/runs/${session.latestId}`}
                  className="group flex items-center justify-between gap-4 rounded-lg border border-border bg-surface px-5 py-4 transition-colors hover:border-border-strong hover:bg-surface-raised"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-medium group-hover:text-primary">
                      {session.title}
                    </p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-1 text-[12.5px] text-faint tabular">
                      {session.turnCount > 1 && (
                        <span className="inline-flex items-center gap-1 font-medium text-muted-foreground">
                          <MessagesSquare className="size-3.5" aria-hidden />
                          {session.turnCount} turns
                        </span>
                      )}
                      {session.turnCount > 1 && <span>·</span>}
                      <span>{formatRelativeTime(session.createdAt)}</span>
                      {session.expertCount > 0 && <span>· {session.expertCount} experts</span>}
                      {session.tokensUsed > 0 && <span>· {formatTokens(session.tokensUsed)} tokens</span>}
                    </p>
                  </div>
                  <RunStatusBadge status={session.status} className="shrink-0" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
