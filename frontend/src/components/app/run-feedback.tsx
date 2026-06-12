"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ThumbsUp, ThumbsDown, ArrowRight, Paperclip, X, MessageSquarePlus } from "lucide-react";
import { useSetRunFeedback, useCreateFollowUp } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { appConfig } from "@/config/app.config";
import { cn } from "@/lib/utils";

/**
 * The post-report footer: a thumbs rating (with an optional note) and a
 * follow-up composer. A follow-up creates a new linked run that threads this
 * report in as context, so the conversation continues instead of dead-ending.
 */
export function RunFeedback({
  runId,
  initialRating,
  canRate = true,
}: {
  runId: string;
  initialRating?: "up" | "down" | null;
  /** Hide the thumbs rating when there's no delivered report to rate
   *  (e.g. a blocked turn) — but still offer the composer to continue. */
  canRate?: boolean;
}) {
  const router = useRouter();
  const toast = useToast();
  const setFeedback = useSetRunFeedback(runId);
  const followUp = useCreateFollowUp(runId);

  const [rating, setRating] = useState<"up" | "down" | null>(initialRating ?? null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");
  const [ask, setAsk] = useState("");
  const [followError, setFollowError] = useState<string | null>(null);
  // attached text files (.md/.txt) — their content is folded into the brief, so
  // it passes through the same sanitize/verify pipeline as typed text
  const [attachments, setAttachments] = useState<{ name: string; content: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  async function attachFiles(files: File[]) {
    setFollowError(null);
    const read = await Promise.all(
      files.map(async (f) => ({ name: f.name, content: (await f.text()).slice(0, 50_000) })),
    );
    setAttachments((prev) => [...prev, ...read].slice(0, 5));
  }

  function effectiveBrief(): string {
    const parts = [ask.trim()];
    for (const a of attachments) parts.push(`\n[Attached file: ${a.name}]\n${a.content}`);
    return parts.filter(Boolean).join("\n").trim();
  }

  function rate(next: "up" | "down") {
    const value = rating === next ? null : next; // click again to clear
    setRating(value);
    setShowComment(value !== null);
    setFeedback.mutate(
      { rating: value, comment: comment.trim() || undefined },
      {
        onSuccess: () =>
          value &&
          toast({ title: "Thanks — feedback saved", tone: "success" }),
      },
    );
  }

  function saveComment() {
    setFeedback.mutate(
      { rating, comment: comment.trim() || undefined },
      { onSuccess: () => toast({ title: "Note saved", tone: "success" }) },
    );
  }

  function sendFollowUp(e: FormEvent) {
    e.preventDefault();
    setFollowError(null);
    followUp.mutate(effectiveBrief(), {
      onSuccess: ({ id }) => router.push(`/app/runs/${id}`),
      onError: (err) =>
        setFollowError(
          err instanceof ApiError ? err.message : "Could not start the follow-up — try again.",
        ),
    });
  }

  // attachments count toward the minimum too — a file alone can carry the brief
  const tooShort = effectiveBrief().length < appConfig.limits.briefMinChars;

  return (
    <section aria-label="Report feedback" className="mt-6">
      {/* rating row — only when there's a delivered report to rate */}
      {canRate && (
      <>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[13px] text-muted-foreground">Was this useful?</span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => rate("up")}
            aria-pressed={rating === "up"}
            aria-label="Helpful"
            className={cn(
              "flex size-10 cursor-pointer items-center justify-center rounded-md border transition-colors",
              rating === "up"
                ? "border-primary bg-primary-soft text-primary"
                : "border-border text-faint hover:border-border-strong hover:text-foreground",
            )}
          >
            <ThumbsUp className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => rate("down")}
            aria-pressed={rating === "down"}
            aria-label="Not helpful"
            className={cn(
              "flex size-10 cursor-pointer items-center justify-center rounded-md border transition-colors",
              rating === "down"
                ? "border-destructive bg-destructive-soft text-destructive"
                : "border-border text-faint hover:border-border-strong hover:text-foreground",
            )}
          >
            <ThumbsDown className="size-4" aria-hidden />
          </button>
        </div>
      </div>

      {showComment && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="fb-comment" className="sr-only">
              What worked or what was off?
            </label>
            <textarea
              id="fb-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={
                rating === "down"
                  ? "What was off? (optional — helps tune the pipeline)"
                  : "What worked well? (optional)"
              }
              rows={2}
              className="w-full resize-none rounded-md border border-border-strong bg-surface-raised px-3.5 py-2.5 text-base leading-relaxed text-foreground placeholder:text-faint focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 sm:text-sm"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={saveComment}
            loading={setFeedback.isPending}
            className="shrink-0"
          >
            Save note
          </Button>
        </div>
      )}
      </>
      )}

      {/* continue the conversation — a distinct, unmissable composer that reads
          as "your turn to reply" rather than just another field on the page */}
      <form
        onSubmit={sendFollowUp}
        className="mt-7 rounded-xl border-2 border-primary/30 bg-primary-soft/30 p-4 shadow-sm"
      >
        <div className="flex items-center gap-2">
          <MessageSquarePlus className="size-4 text-primary" aria-hidden />
          <label htmlFor="followup" className="text-sm font-semibold text-foreground">
            Continue the conversation
          </label>
        </div>
        <p className="mt-0.5 pl-6 text-[12px] text-muted-foreground">
          Stays in this session — everything above is carried along as context.
        </p>

        <div className="mt-3 overflow-hidden rounded-lg border border-border-strong bg-surface-raised transition-colors focus-within:border-primary">
          <textarea
            id="followup"
            value={ask}
            onChange={(e) => setAsk(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Reply to keep going — dig deeper, narrow the scope, or attach a file…"
            rows={3}
            className="w-full resize-none bg-transparent px-4 py-3 text-base leading-relaxed placeholder:text-faint focus:outline-none sm:text-[15px]"
          />

          {/* attached files */}
          {attachments.length > 0 && (
            <ul className="flex flex-wrap gap-2 px-3 pb-2">
              {attachments.map((a, i) => (
                <li
                  key={`${a.name}-${i}`}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-muted-foreground"
                >
                  <Paperclip className="size-3 shrink-0 text-faint" aria-hidden />
                  <span className="truncate">{a.name}</span>
                  <button
                    type="button"
                    onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                    aria-label={`Remove ${a.name}`}
                    className="flex size-5 shrink-0 cursor-pointer items-center justify-center rounded text-faint hover:text-destructive"
                  >
                    <X className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center justify-between gap-2 border-t border-border bg-background/40 px-3 py-2.5">
            <div className="flex items-center gap-3">
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
                accept=".md,.markdown,.txt,text/plain,text/markdown"
                multiple
                className="hidden"
                aria-label="Attach text files to your follow-up"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  e.target.value = "";
                  if (files.length) attachFiles(files);
                }}
              />
              <span className="text-[12px] text-faint" aria-live="polite">
                {tooShort && effectiveBrief().length > 0
                  ? `${appConfig.limits.briefMinChars - effectiveBrief().length} more characters`
                  : "Continues this session"}
              </span>
            </div>
            <Button type="submit" size="sm" loading={followUp.isPending} disabled={tooShort}>
              {followUp.isPending ? "Sending…" : "Send"}
              {!followUp.isPending && <ArrowRight className="size-4" aria-hidden />}
            </Button>
          </div>
        </div>
        {followError && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {followError}
          </p>
        )}
      </form>
    </section>
  );
}
