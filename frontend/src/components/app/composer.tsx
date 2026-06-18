"use client";

import { useRef, type FormEvent } from "react";
import { ArrowUp, Plus, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
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
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (files: File[], models: Record<string, string>) => void;
  pending?: boolean;
  submitError?: string | null;
  placeholder?: string;
  autoFocus?: boolean;
  rows?: number;
  /** A run is in flight — the send button becomes a Stop, and Enter is disarmed
   *  (you can still type your next message while it works). */
  busy?: boolean;
  onStop?: () => void;
  className?: string;
}) {
  const attach = useFileAttachments();
  const session = useSessionModels();
  const fileRef = useRef<HTMLInputElement>(null);
  const taRef = useAutoResize(value, 280);

  const tooShort = value.trim().length < appConfig.limits.briefMinChars;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (tooShort || pending) return;
    onSubmit(attach.files, session.models);
  }

  return (
    <form onSubmit={submit} className={className} aria-label="Message Clannon">
      <div
        {...attach.dropZoneProps}
        className={cn(
          "relative overflow-hidden rounded-2xl border border-border-strong bg-surface-raised shadow-sm transition-colors focus-within:border-primary",
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
              !tooShort &&
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
          className="max-h-[280px] w-full resize-none overflow-y-auto bg-transparent px-4 py-3.5 text-base leading-relaxed placeholder:text-faint focus:outline-none sm:text-[15px]"
        />
        <AttachmentChips files={attach.files} onRemove={attach.removeFile} />
        <HeavyMediaNote show={attach.hasHeavyMedia} />

        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <Tooltip label="Attach files" align="start">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              aria-label="Attach files"
              className="flex size-9 cursor-pointer items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
          {/* model selector + send/stop, grouped on the right */}
          <div className="flex items-center gap-1">
            <SessionModelPicker models={session.models} onSetRole={session.setRole} />
            {busy && onStop ? (
              <Tooltip label="Stop" align="end">
                <button
                  type="button"
                  onClick={onStop}
                  aria-label="Stop the run"
                  className="flex size-9 cursor-pointer items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-90"
                >
                  <Square className="size-3 fill-current" aria-hidden />
                </button>
              </Tooltip>
            ) : (
              <Tooltip label="Send" align="end">
                <Button
                  type="submit"
                  size="sm"
                  loading={pending}
                  disabled={tooShort}
                  aria-label="Send"
                  className="size-9 rounded-full !px-0"
                >
                  {!pending && <ArrowUp className="size-4" aria-hidden />}
                </Button>
              </Tooltip>
            )}
          </div>
        </div>
      </div>
      {(submitError || attach.error) && (
        <p role="alert" className="mt-2 px-1 text-sm text-destructive">
          {submitError || attach.error}
        </p>
      )}
    </form>
  );
}
