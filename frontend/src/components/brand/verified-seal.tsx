import { cn } from "@/lib/utils";

/**
 * The verified seal — the promise ("checked against its source before it
 * reaches you") made into an OBJECT. It speaks the product's ONE visual
 * language: smooth concentric growth rings (the dendrochronology mark, the
 * archive target), NOT a certificate sunburst. Verification is another ring
 * laid down. The check is pressed at the dead centre; the whole stamp is
 * embossed into the sheet (a letterpress highlight below the ink) and tilted
 * a few degrees so it reads as landed by hand, not printed by a template.
 *
 * `state` follows the persisted output-filter verdict
 * (`reports/INTEGRATION_CONTRACT.md` §5): "grounded" is the full earned
 * stamp (moss ink, complete check). "partial" is the SAME rings — still
 * something was checked — but muted (never `text-primary`, and never the
 * `warning`/amber token: amber means memory in this product, not a
 * verification qualifier) with a short tick instead of a full check, so it
 * never reads as fully earned. "ungrounded" and "not_applicable" don't use
 * this component at all — see the run page's own branching.
 */
export function VerifiedSeal({
  className,
  state = "grounded",
}: {
  className?: string;
  state?: "grounded" | "partial";
}) {
  const partial = state === "partial";
  return (
    <svg
      viewBox="0 0 48 48"
      className={cn(
        partial ? "text-muted-foreground" : "text-primary",
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
      <circle cx="24" cy="24" r="12" fill="none" stroke="currentColor" strokeWidth="2.3" opacity={partial ? 0.75 : 1} />
      {partial ? (
        /* a short tick, not a full check — some support exists, not a clean pass */
        <path d="M18.5 25 L22.5 29" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" />
      ) : (
        /* the check, struck through the pith */
        <path
          d="M17.5 24.5 L22 29 L31 17.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}
