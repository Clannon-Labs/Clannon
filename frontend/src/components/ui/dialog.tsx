"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** How long the sheet-out animation runs before the dialog actually closes. */
const CLOSE_MS = 170;

/**
 * Accessible modal on the native <dialog> element: focus trapping,
 * Escape handling, and top-layer rendering come from the platform.
 * Closing is choreographed: the panel plays its exit animation first,
 * then the element closes (Escape is intercepted so it exits the same way).
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      dialog.style.animation = ""; // back to the class-driven entrance
      if (!dialog.open) dialog.showModal();
      return;
    }
    if (dialog.open) {
      // inline style outranks the open: entrance class while the exit plays
      dialog.style.animation = `sheet-out ${CLOSE_MS / 1000}s ease-in both`;
      const t = window.setTimeout(() => {
        dialog.close();
        dialog.style.animation = "";
      }, CLOSE_MS);
      return () => window.clearTimeout(t);
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        // Escape: run the same animated close instead of the instant native one
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        // click on the backdrop (the dialog element itself) dismisses
        if (e.target === ref.current) onClose();
      }}
      className={cn(
        "m-auto w-[calc(100vw-2rem)] max-w-md rounded-lg border border-border bg-surface-raised p-0 text-foreground shadow-2xl",
        "backdrop:bg-black/55 backdrop:backdrop-blur-[2px]",
        "open:animate-sheet-in",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <h2 id={titleId} className="display-soft text-lg">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="-mr-2 flex size-10 cursor-pointer items-center justify-center rounded-sm text-faint transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  );
}
