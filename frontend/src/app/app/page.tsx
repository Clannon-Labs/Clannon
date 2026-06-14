"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowRight, MessagesSquare, Paperclip, Sprout, X } from "lucide-react";
import { useCreateRun, useMe, useRuns } from "@/lib/api/hooks";
import { ApiError, type RunSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import { RunStatusBadge } from "@/components/app/run-status";
import { HydrationPanel } from "@/components/app/hydration-panel";
import { cn, formatBytes, formatRelativeTime, formatTokens } from "@/lib/utils";

import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";
import { appConfig } from "@/config/app.config";

// Input-file limits. These MIRROR the backend for fast feedback only — the
// backend stays the authority and its 422 (which file, why) is surfaced verbatim.
const MAX_FILES = 10;
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ACCEPTED_INPUT =
  ".txt,.md,.markdown,.csv,.tsv,.json,.jsonl,.yaml,.yml,.xml,.html,.htm,.log,.rtf,.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff,.mp3,.wav,.m4a,.aac,.ogg,.flac,.mp4,.mov,.webm,.avi";
const TEXT_LIKE = /\.(txt|md|markdown|csv|tsv|json|jsonl|ya?ml|xml|html?|log|rtf)$/i;
// Images, audio, and video are all live upload types now (the Media Expert reads
// the three via Gemini). .svg is intentionally excluded — a vector/XSS-shaped
// format we don't invite from the UI.
const IMAGE_LIKE = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i;
const AUDIO_LIKE = /\.(mp3|wav|m4a|aac|ogg|flac)$/i;
const VIDEO_LIKE = /\.(mp4|mov|webm|avi)$/i;

/** A reason to reject a file before upload, or null if it's acceptable today. */
function rejectInputFile(file: File): string | null {
  if (file.size > MAX_FILE_BYTES) return `${file.name} is larger than 50 MB.`;
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  const isText = file.type.startsWith("text/") || TEXT_LIKE.test(file.name);
  const isImage =
    (file.type.startsWith("image/") && file.type !== "image/svg+xml") ||
    IMAGE_LIKE.test(file.name);
  const isAudio = file.type.startsWith("audio/") || AUDIO_LIKE.test(file.name);
  const isVideo = file.type.startsWith("video/") || VIDEO_LIKE.test(file.name);
  if (!isPdf && !isText && !isImage && !isAudio && !isVideo) {
    return `${file.name}: only text files, PDFs, images, audio, and video are supported.`;
  }
  return null;
}

/** Audio/video, which can be heavy enough to exceed the model's inline limit. */
function isAudioOrVideo(file: File): boolean {
  return (
    file.type.startsWith("audio/") ||
    file.type.startsWith("video/") ||
    AUDIO_LIKE.test(file.name) ||
    VIDEO_LIKE.test(file.name)
  );
}

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
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  // depth counter so dragenter/leave over child nodes doesn't flicker the state
  const dragDepth = useRef(0);

  const firstName = user?.name.split(" ")[0] ?? "";
  const tooShort = brief.trim().length < appConfig.limits.briefMinChars;
  const hasHeavyMedia = files.some(isAudioOrVideo);

  function addFiles(picked: File[]) {
    setError(null);
    const next = [...files];
    for (const f of picked) {
      if (next.length >= MAX_FILES) {
        setError(`Up to ${MAX_FILES} files per run.`);
        break;
      }
      if (next.some((e) => e.name === f.name && e.size === f.size)) continue; // dedupe
      const reason = rejectInputFile(f);
      if (reason) {
        setError(reason);
        continue;
      }
      next.push(f);
    }
    setFiles(next);
  }

  // collapse a multi-turn conversation into ONE entry: a session shows the
  // original ask as its title, links to the latest turn (which renders the full
  // thread), and aggregates turn count + tokens.
  const sessions = useMemo(() => groupBySession(runs), [runs]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createRun.mutate(
      { brief, files },
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
          onDragEnter={(e) => {
            e.preventDefault();
            dragDepth.current += 1;
            setDragOver(true);
          }}
          onDragOver={(e) => e.preventDefault()} // allow drop
          onDragLeave={(e) => {
            e.preventDefault();
            dragDepth.current -= 1;
            if (dragDepth.current <= 0) {
              dragDepth.current = 0;
              setDragOver(false);
            }
          }}
          onDrop={(e) => {
            e.preventDefault();
            dragDepth.current = 0;
            setDragOver(false);
            const dropped = Array.from(e.dataTransfer.files);
            if (dropped.length) addFiles(dropped); // same validation as the picker
          }}
          className={cn(
            "relative overflow-hidden rounded-lg border border-border-strong bg-surface transition-colors focus-within:border-primary",
            dragOver && "border-primary ring-2 ring-primary/30",
          )}
        >
          {dragOver && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-primary-soft/80 backdrop-blur-sm">
              <span className="flex items-center gap-2 text-sm font-medium text-primary">
                <Paperclip className="size-4" aria-hidden /> Drop files to attach
              </span>
            </div>
          )}
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
          {/* attached input files — removable before submit */}
          {files.length > 0 && (
            <ul className="flex flex-wrap gap-2 px-4 pb-1">
              {files.map((f, i) => (
                <li
                  key={`${f.name}-${f.size}-${i}`}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-muted-foreground"
                >
                  <Paperclip className="size-3 shrink-0 text-faint" aria-hidden />
                  <span className="truncate">{f.name}</span>
                  <span className="shrink-0 text-faint tabular">{formatBytes(f.size)}</span>
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    aria-label={`Remove ${f.name}`}
                    className="flex size-5 shrink-0 cursor-pointer items-center justify-center rounded text-faint hover:text-destructive"
                  >
                    <X className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {hasHeavyMedia && (
            <p className="px-4 pb-1 text-[12px] text-faint">
              A very large audio or video can exceed the model&apos;s inline limit — that one run fails gracefully if so.
            </p>
          )}
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
                onChange={(e) => {
                  const picked = Array.from(e.target.files ?? []);
                  e.target.value = ""; // allow re-picking the same file
                  if (picked.length) addFiles(picked);
                }}
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
        {error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {error}
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
