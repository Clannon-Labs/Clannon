"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import { appConfig } from "@/config/app.config";
import { ApiError, type Run } from "@/lib/api";
import { copyText } from "@/lib/copy-text";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type RevisePrompt = (runId: string, brief: string) => Promise<void>;

/**
 * One sent prompt and its stable client-side actions. Pointer users reveal the
 * actions by hovering/focusing the bubble; touch users tap the bubble. Editing
 * happens in place, where the prompt lives — never inside the decision log.
 */
export function TurnPrompt({
  turn,
  laterTurnCount = 0,
  onRevise,
  className,
}: {
  turn: Run;
  laterTurnCount?: number;
  onRevise?: RevisePrompt;
  className?: string;
}) {
  const [actionsOpen, setActionsOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(turn.brief);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      const editor = editorRef.current;
      editor?.focus();
      const end = editor?.value.length ?? 0;
      editor?.setSelectionRange(end, end);
    }
  }, [editing]);

  async function copyPrompt() {
    try {
      await copyText(turn.brief);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Could not copy this prompt. Select the text and copy it manually.");
    }
  }

  function startEditing() {
    setDraft(turn.brief);
    setError(null);
    setEditing(true);
    setActionsOpen(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const brief = draft.trim();
    if (!onRevise || pending) return;
    if (brief.length < appConfig.limits.briefMinChars) {
      setError("Keep at least two characters in the prompt.");
      return;
    }

    setPending(true);
    setError(null);
    try {
      await onRevise(turn.id, brief);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not restart from this prompt. Your original conversation is unchanged.",
      );
      setPending(false);
    }
  }

  if (editing) {
    return (
      <form
        onSubmit={submit}
        className={cn(
          "ml-auto w-[min(100%,40rem)] rounded-xl border border-border-strong bg-surface-raised p-3 shadow-md",
          className,
        )}
      >
        <label htmlFor={`edit-prompt-${turn.id}`} className="tag-label text-faint">
          Edit sent prompt
        </label>
        <textarea
          ref={editorRef}
          id={`edit-prompt-${turn.id}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setEditing(false);
              setError(null);
            }
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          rows={5}
          className="mt-2 w-full resize-y rounded-md border border-border bg-background px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
        />
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          {laterTurnCount > 0
            ? `Submitting removes this turn and its response, then replaces them with your edit. ${laterTurnCount} later ${
                laterTurnCount === 1 ? "turn" : "turns"
              } will also be removed from this conversation. Saved memory remains available.`
            : "Submitting removes this turn and its response, then replaces them with your edit. Saved memory remains available."}
        </p>
        {error && (
          <p role="alert" className="mt-2 text-[12px] leading-relaxed text-destructive">
            {error}
          </p>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => {
              setEditing(false);
              setError(null);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" size="sm" loading={pending}>
            Restart from here
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className={cn("group/prompt relative flex flex-col items-end", className)}>
      <button
        type="button"
        onClick={() => setActionsOpen((open) => !open)}
        aria-expanded={actionsOpen}
        className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md border border-border bg-surface-raised px-4 py-2.5 text-left text-sm leading-relaxed text-foreground transition-colors hover:border-border-strong"
      >
        {turn.brief}
        <span className="sr-only"> — show prompt actions</span>
      </button>

      <div
        aria-label="Prompt actions"
        className={cn(
          "mt-1 items-center gap-0.5",
          actionsOpen ? "flex" : "hidden",
          "md:absolute md:right-full md:top-1/2 md:mr-1 md:mt-0 md:flex md:-translate-y-1/2 md:opacity-0 md:transition-opacity md:group-hover/prompt:opacity-100 md:group-focus-within/prompt:opacity-100",
        )}
      >
        <Tooltip label={copied ? "Copied" : "Copy prompt"} side="top">
          <button
            type="button"
            onClick={copyPrompt}
            aria-label="Copy sent prompt"
            className="flex size-9 items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
          >
            {copied ? (
              <Check className="size-3.5 text-primary" aria-hidden />
            ) : (
              <Copy className="size-3.5" aria-hidden />
            )}
          </button>
        </Tooltip>
        {onRevise && (
          <Tooltip label="Edit prompt" side="top">
            <button
              type="button"
              onClick={startEditing}
              aria-label="Edit sent prompt"
              className="flex size-9 items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              <Pencil className="size-3.5" aria-hidden />
            </button>
          </Tooltip>
        )}
      </div>

      {error && !editing && (
        <p role="alert" className="mt-1 max-w-[85%] text-[12px] text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
