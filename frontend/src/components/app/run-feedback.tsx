"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ThumbsUp, ThumbsDown, ArrowRight, Paperclip, MessageSquarePlus } from "lucide-react";
import { useSetRunFeedback, useCreateFollowUp } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  useFileAttachments,
  AttachmentChips,
  DropOverlay,
  HeavyMediaNote,
} from "@/components/app/attachments";
import { ACCEPTED_INPUT } from "@/lib/uploads";
import { appConfig } from "@/config/app.config";
import { cn } from "@/lib/utils";

/**
 * The post-report footer. It LEADS with a "continue the conversation" composer —
 * a new linked run in the same session that threads this report in as context —
 * with a small, secondary thumbs rating beneath it. The composer takes files of
 * every type a root run does (real multipart upload, not text-inlining).
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
  const attach = useFileAttachments();
  const fileRef = useRef<HTMLInputElement>(null);

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
    followUp.mutate(
      { brief: ask, files: attach.files },
      {
        onSuccess: ({ id }) => router.push(`/app/runs/${id}`),
        onError: (err) =>
          setFollowError(
            err instanceof ApiError ? err.message : "Could not start the follow-up — try again.",
          ),
      },
    );
  }

  const tooShort = ask.trim().length < appConfig.limits.briefMinChars;

  return (
    <section aria-label="Continue the conversation" className="mt-6">
      {/* PRIMARY: continue the conversation — a distinct, unmissable composer that
          reads as "your turn to reply", taking files of every supported type */}
      <form
        onSubmit={sendFollowUp}
        className="rounded-xl border-2 border-primary/30 bg-primary-soft/30 p-4 shadow-sm"
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

        <div
          {...attach.dropZoneProps}
          className={cn(
            "relative mt-3 overflow-hidden rounded-lg border border-border-strong bg-surface-raised transition-colors focus-within:border-primary",
            attach.dragOver && "border-primary ring-2 ring-primary/30",
          )}
        >
          <DropOverlay show={attach.dragOver} />
          <textarea
            id="followup"
            value={ask}
            onChange={(e) => setAsk(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift/Cmd/Ctrl+Enter insert a newline. Guard IME
              // composition, the empty/too-short case, and an in-flight send.
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.metaKey &&
                !e.ctrlKey &&
                !e.altKey &&
                !e.nativeEvent.isComposing &&
                !tooShort &&
                !followUp.isPending
              ) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Reply to keep going — dig deeper, narrow the scope, or attach a file…"
            rows={3}
            className="w-full resize-none bg-transparent px-4 py-3 text-base leading-relaxed placeholder:text-faint focus:outline-none sm:text-[15px]"
          />
          <AttachmentChips files={attach.files} onRemove={attach.removeFile} />
          <HeavyMediaNote show={attach.hasHeavyMedia} />

          <div className="flex items-center justify-between gap-2 border-t border-border bg-background/40 px-3 py-2.5">
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
                aria-label="Attach files to your follow-up — text, PDF, image, audio, or video"
                onChange={attach.handlePicked}
              />
              <span className="text-[12px] text-faint" aria-live="polite">
                {tooShort && ask.trim().length > 0
                  ? `${appConfig.limits.briefMinChars - ask.trim().length} more characters`
                  : "Continues this session"}
              </span>
            </div>
            <Button type="submit" size="sm" loading={followUp.isPending} disabled={tooShort}>
              {followUp.isPending ? "Sending…" : "Send"}
              {!followUp.isPending && <ArrowRight className="size-4" aria-hidden />}
            </Button>
          </div>
        </div>
        {(followError || attach.error) && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {followError || attach.error}
          </p>
        )}
      </form>

      {/* SECONDARY: was this useful? — a quiet rating beneath the composer, shown
          only when there's a delivered report to rate */}
      {canRate && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[12.5px] text-faint">Was this useful?</span>
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
        </div>
      )}
    </section>
  );
}
