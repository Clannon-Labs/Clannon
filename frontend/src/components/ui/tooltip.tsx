import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A small, dependency-free tooltip. Shows on hover (mouse) and on focus-within —
 * and because tapping a control focuses it, touch users get the same tip on tap.
 * Wrap a focusable control (button/link). Keep `label` short unless `wide`.
 */
export function Tooltip({
  label,
  children,
  side = "top",
  align = "center",
  wide = false,
  className,
}: {
  label: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom";
  align?: "center" | "start" | "end";
  wide?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 rounded-md border border-border bg-surface-raised px-2 py-1 text-[12px] font-medium leading-snug text-foreground opacity-0 shadow-md transition-opacity duration-150 group-hover/tt:opacity-100 group-focus-within/tt:opacity-100",
          wide ? "max-w-[15rem] whitespace-normal" : "whitespace-nowrap",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
          align === "center" && "left-1/2 -translate-x-1/2",
          align === "start" && "left-0",
          align === "end" && "right-0",
        )}
      >
        {label}
      </span>
    </span>
  );
}

/**
 * The little ⓘ info button — a touch-friendly way to read the same tip a mouse
 * user gets on hover. Tapping it focuses the button, which reveals the tooltip.
 */
export function InfoTip({
  label,
  side = "top",
  align = "center",
  className,
}: {
  label: ReactNode;
  side?: "top" | "bottom";
  align?: "center" | "start" | "end";
  className?: string;
}) {
  return (
    <Tooltip label={label} side={side} align={align} wide className={cn("align-middle", className)}>
      <button
        type="button"
        aria-label="More information"
        onClick={(e) => e.preventDefault()}
        className="inline-flex size-4 cursor-help items-center justify-center rounded-full text-faint transition-colors hover:text-muted-foreground focus-visible:text-foreground"
      >
        <Info className="size-3.5" aria-hidden />
      </button>
    </Tooltip>
  );
}
