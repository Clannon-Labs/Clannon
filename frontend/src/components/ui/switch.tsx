"use client";

import { cn } from "@/lib/utils";

/** A real on/off switch — the settings surface has segmented controls
 *  (`ThemeSegment`) and checkboxes-as-cards elsewhere, but nothing binary
 *  and inline. `role="switch"` + `aria-checked` (not a native checkbox) so
 *  the visual pill can match the rest of the design system's controls. */
export function Switch({
  checked,
  onCheckedChange,
  disabled = false,
  label,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
  /** Accessible name — this control never carries visible text of its own. */
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full border transition-colors",
        checked ? "border-primary bg-primary" : "border-border-strong bg-muted",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-4 rounded-full bg-background shadow-sm transition-transform",
          checked ? "translate-x-[19px]" : "translate-x-[3px]",
        )}
      />
    </button>
  );
}
