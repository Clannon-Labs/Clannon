"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useBudgetExhausted, useSetRunFeedback, useCreateFollowUp, useMe, useUsage } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Composer } from "@/components/app/composer";
import {
  runReplyDraftKey,
} from "@/lib/browser-drafts";
import { useBrowserTextDraft } from "@/lib/use-browser-draft";
import { cn } from "@/lib/utils";

/**
 * The docked reply composer — a new linked turn in the same session that threads
 * the whole conversation in as context. Uses the shared <Composer>, so it's the
 * same control as the new-chat screen; it just sends a follow-up instead.
 */
export function RunComposer({
  runId,
  busy,
  onStop,
  className,
}: {
  runId: string;
  /** A run in this session is still in flight — show Stop instead of Send. */
  busy?: boolean;
  onStop?: () => void;
  className?: string;
}) {
  const router = useRouter();
  const { data: user } = useMe();
  const followUp = useCreateFollowUp(runId);
  const budgetExhausted = useBudgetExhausted();
  const { data: budgetUsage } = useUsage();
  const [followError, setFollowError] = useState<string | ApiError | null>(null);
  const draftKey = user?.id ? runReplyDraftKey(user.id, runId) : null;
  const [ask, setAsk] = useBrowserTextDraft(draftKey);

  return (
    <div className={className}>
      <Composer
        value={ask}
        onChange={setAsk}
        pending={followUp.isPending}
        submitError={followError}
        budgetExhausted={budgetExhausted}
        budgetUsage={budgetUsage}
        busy={busy}
        onStop={onStop}
        placeholder={
          busy
            ? "Write your next message — Send unlocks when this run finishes…"
            : "Reply to continue — dig deeper, narrow the scope, or attach a file…"
        }
        onSubmit={(files, models) => {
          setFollowError(null);
          followUp.mutate(
            { brief: ask, files, models },
            {
              onSuccess: ({ id }) => {
                setAsk("");
                router.push(`/app/runs/${id}`);
              },
              onError: (err) => setFollowError(
                err instanceof ApiError
                  ? err
                  : "Could not start the follow-up — try again.",
              ),
            },
          );
        }}
      />
      {busy && (
        <p role="status" className="mt-2 px-2 text-[12px] leading-relaxed text-faint">
          Safe to leave this page — work continues. Usage posts after delivery.
          Your typed reply stays in this tab.
        </p>
      )}
    </div>
  );
}

/**
 * The per-report rating — a quiet thumbs (+ optional note), shown beneath a
 * delivered report. Secondary to the composer; only rendered when there's a
 * report to rate.
 */
export function ReportRating({
  runId,
  initialRating,
}: {
  runId: string;
  initialRating?: "up" | "down" | null;
}) {
  const toast = useToast();
  const setFeedback = useSetRunFeedback(runId);

  const [rating, setRating] = useState<"up" | "down" | null>(initialRating ?? null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState("");

  function rate(next: "up" | "down") {
    const value = rating === next ? null : next; // click again to clear
    setRating(value);
    setShowComment(value !== null);
    setFeedback.mutate(
      { rating: value, comment: comment.trim() || undefined },
      { onSuccess: () => value && toast({ title: "Thanks — feedback saved", tone: "success" }) },
    );
  }

  function saveComment() {
    setFeedback.mutate(
      { rating, comment: comment.trim() || undefined },
      { onSuccess: () => toast({ title: "Note saved", tone: "success" }) },
    );
  }

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[12px] text-faint">Was this useful?</span>
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
  );
}
