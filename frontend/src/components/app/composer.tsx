"use client";

import { useEffect, useRef, type FormEvent } from "react";
import { ArrowUp, Plus, Square, Star } from "lucide-react";
import { ApiError, type UsageSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { BudgetExhaustedNotice } from "@/components/app/budget-exhausted-notice";
import {
  useFileAttachments,
  AttachmentChips,
  DropOverlay,
  HeavyMediaNote,
} from "@/components/app/attachments";
import { useSessionModels, SessionModelPicker } from "@/components/app/model-picker";
import { Tooltip } from "@/components/ui/tooltip";
import { ACCEPTED_INPUT } from "@/lib/uploads";
import { useAutoResize } from "@/lib/use-auto-resize";
import { appConfig } from "@/config/app.config";
import { formatDurationEstimate } from "@/lib/usage-forecast";
import { cn, isFinePointer } from "@/lib/utils";

/**
 * The one composer, used everywhere a user types to Clannon — the new-chat
 * screen and the docked reply on a run. Same control layout in both places
 * (rounded field, attach, per-run model overrides, round send button) so there's
 * nothing app-specific to relearn. The parent owns the text `value` (so example
 * chips can fill it); the composer owns attachments + model overrides and hands
 * them back on submit.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  pending = false,
  submitError,
  placeholder = "Message Clannon…",
  autoFocus = false,
  rows = 3,
  busy = false,
  onStop,
  className,
  budgetExhausted = false,
  budgetUsage,
  onSaveTemplate,
  loadTemplate,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (files: File[], models: Record<string, string>) => void;
  pending?: boolean;
  submitError?: string | ApiError | null;
  placeholder?: string;
  autoFocus?: boolean;
  rows?: number;
  /** A run is in flight — the send button becomes a Stop, and Enter is disarmed
   *  (you can still type your next message while it works). */
  busy?: boolean;
  onStop?: () => void;
  className?: string;
  /** The account is out of tokens this period. Blocks submission here too —
   *  the sidebar's own exhausted card said so, but Send stayed live until
   *  this existed, a real gap since the sidebar isn't always in view
   *  (collapsed rail, mobile). Typing still works; only sending is gated. */
  budgetExhausted?: boolean;
  budgetUsage?: UsageSummary;
  /** Present only where saved templates apply (the new-run composer, not a
   *  run's reply box) — omit to hide the trigger entirely. Called with the
   *  current session model overrides; the caller owns naming/storage. */
  onSaveTemplate?: (models: Record<string, string>) => void;
  /** Set when a saved template is "used" — applies its model overrides to
   *  this session. `token` must change on every apply (even reusing the same
   *  template twice in a row) since it's the effect's only trigger; the
   *  brief text itself loads through the ordinary `value`/`onChange` pair. */
  loadTemplate?: { token: string; models?: Record<string, string> } | null;
}) {
  const attach = useFileAttachments();
  const session = useSessionModels();
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useAutoResize(value, 280);

  useEffect(() => {
    if (!loadTemplate) return;
    session.replace(loadTemplate.models ?? {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadTemplate?.token]);

  const durationEstimate = formatDurationEstimate(budgetUsage);
  const tooShort = value.trim().length < appConfig.limits.briefMinChars;
  const admissionExhausted = submitError instanceof ApiError
    && submitError.status === 402
    && submitError.code === "token_budget_exhausted";
  const blocked = tooShort || budgetExhausted || admissionExhausted;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (blocked || pending) return;
    onSubmit(attach.files, session.models);
  }

  return (
    <form onSubmit={submit} className={className} aria-label="Message Clannon">
      <div
        {...attach.dropZoneProps}
        className={cn(
          // dark: edge-light + a real drop shadow — the composer is an instrument
          // on the desk, not an outline on the wall
          "relative overflow-hidden rounded-3xl border border-border-strong bg-surface-raised shadow-sm transition-colors focus-within:border-primary dark:[box-shadow:inset_0_1px_0_0_var(--edge-light),0_8px_24px_-12px_rgb(0_0_0/0.6)]",
          attach.dragOver && "border-primary ring-2 ring-primary/30",
        )}
      >
        <DropOverlay show={attach.dragOver} />
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={taRef}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Desktop: Enter sends, Shift/Cmd/Ctrl+Enter newline. Touch: the
            // return key always inserts a newline (Send is the only path).
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.metaKey &&
              !e.ctrlKey &&
              !e.altKey &&
              !e.nativeEvent.isComposing &&
              !blocked &&
              !pending &&
              !busy &&
              isFinePointer()
            ) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={placeholder}
          rows={rows}
          className="max-h-[280px] w-full resize-none overflow-y-auto bg-transparent px-5 py-4 text-base leading-relaxed placeholder:text-faint focus:outline-none sm:px-4 sm:py-3.5 sm:text-[15px]"
        />
        <AttachmentChips files={attach.files} onRemove={attach.removeFile} />
        <HeavyMediaNote show={attach.hasHeavyMedia} />

        <div className="flex items-center justify-between gap-2 px-3 pb-3 sm:px-2.5 sm:pb-2.5">
          <Tooltip label="Attach files" align="start">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              aria-label="Attach files"
              className="flex size-10 cursor-pointer items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:size-9"
            >
              <Plus className="size-4" aria-hidden />
            </button>
          </Tooltip>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_INPUT}
            multiple
            className="hidden"
            aria-label="Attach files — text, PDF, image, audio, or video"
            onChange={attach.handlePicked}
          />
          {onSaveTemplate && (
            <Tooltip label="Save as template" align="start">
              <button
                type="button"
                onClick={() => onSaveTemplate(session.models)}
                disabled={tooShort}
                aria-label="Save as template"
                className="flex size-10 cursor-pointer items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-muted-foreground sm:size-9"
              >
                <Star className="size-4" aria-hidden />
              </button>
            </Tooltip>
          )}
          {/* model selector + send/stop, grouped on the right */}
          <div className="flex items-center gap-1">
            <SessionModelPicker
              models={session.models}
              onSetRole={session.setRole}
              onSetAll={session.setAll}
            />
            {busy && onStop ? (
              <Tooltip label="Stop" align="end">
                <button
                  type="button"
                  onClick={onStop}
                  aria-label="Stop the run"
                  className="flex size-10 cursor-pointer items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-90 sm:size-9"
                >
                  <Square className="size-3 fill-current" aria-hidden />
                </button>
              </Tooltip>
            ) : (
              <Tooltip label="Send" align="end">
                <Button
                  type="submit"
                  size="icon"
                  loading={pending}
                  disabled={blocked}
                  aria-label="Send"
                  className="size-10 sm:size-9"
                >
                  {!pending && <ArrowUp className="size-4" aria-hidden />}
                </Button>
              </Tooltip>
            )}
          </div>
        </div>
      </div>
      {(budgetExhausted || admissionExhausted) ? (
        <BudgetExhaustedNotice
          error={submitError instanceof ApiError ? submitError : undefined}
          usage={budgetUsage}
          forced={budgetExhausted}
        />
      ) : submitError || attach.error ? (
        <p role="alert" className="mt-2 px-1 text-sm text-destructive">
          {submitError instanceof ApiError ? submitError.message : submitError || attach.error}
        </p>
      ) : (
        // set expectations before Send, not just narrate progress after —
        // sourced from the account's own recent runs (usage-forecast.ts),
        // never shown while there's nothing to estimate from yet
        !busy &&
        !pending &&
        value.trim().length > 0 &&
        durationEstimate && (
          <p className="mt-2 px-1 text-[12px] text-faint">
            Runs like this usually take {durationEstimate}.
          </p>
        )
      )}
    </form>
  );
}
