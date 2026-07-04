import { cn } from "@/lib/utils";

/**
 * The verified seal — the promise ("checked against its source before it
 * reaches you") made into an OBJECT. It speaks the product's ONE visual
 * language: smooth concentric growth rings (the dendrochronology mark, the
 * archive target), NOT a certificate sunburst. Verification is another ring
 * laid down. The check is pressed at the dead centre; the whole stamp is
 * embossed into the sheet (a letterpress highlight below the ink) and tilted
 * a few degrees so it reads as landed by hand, not printed by a template.
 */
export function VerifiedSeal({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      className={cn(
        "text-primary",
        // letterpress: a highlight below the ink reads as "pressed into" the
        // sheet. Light sheet → white highlight; dark sheet → a dark deboss.
        "[filter:drop-shadow(0_0.6px_0_rgb(255_255_255/0.6))]",
        "dark:[filter:drop-shadow(0_0.6px_0.5px_rgb(0_0_0/0.55))]",
        className,
      )}
      style={{ transform: "rotate(-6deg)" }}
      aria-hidden
    >
      {/* the rings — same family as the brand mark, laid down oldest (faint,
          outer) to newest (bold, inner) */}
      <circle cx="24" cy="24" r="21" fill="none" stroke="currentColor" strokeWidth="1.3" opacity="0.38" />
      <circle cx="24" cy="24" r="16.5" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.62" />
      <circle cx="24" cy="24" r="12" fill="none" stroke="currentColor" strokeWidth="2.3" />
      {/* the check, struck through the pith */}
      <path
        d="M17.5 24.5 L22 29 L31 17.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
