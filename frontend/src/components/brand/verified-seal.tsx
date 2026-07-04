import { cn } from "@/lib/utils";

/**
 * The verified seal — the promise ("checked against its source before it
 * reaches you") made into an OBJECT, not a status badge. Concentric stamp
 * rings echo the memory dendrochronology; a serrated outer edge reads as a
 * pressed seal; the check is struck through the middle. Rendered in moss
 * (verified is always moss), embossed into the sheet with a faint highlight
 * so it looks pressed, not printed. The tiny counter-rotation keeps it from
 * feeling machine-perfect — a stamp landed by hand.
 */
export function VerifiedSeal({ className }: { className?: string }) {
  // 24 serration ticks around the rim — the stamp's milled edge
  const ticks = Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2;
    const r1 = 21.5;
    const r2 = 23;
    return {
      x1: 24 + Math.cos(a) * r1,
      y1: 24 + Math.sin(a) * r1,
      x2: 24 + Math.cos(a) * r2,
      y2: 24 + Math.sin(a) * r2,
    };
  });
  return (
    <svg
      viewBox="0 0 48 48"
      className={cn("text-primary [filter:drop-shadow(0_0.5px_0_rgb(255_255_255/0.55))] dark:[filter:none]", className)}
      style={{ transform: "rotate(-7deg)" }}
      aria-hidden
    >
      {ticks.map((t, i) => (
        <line
          key={i}
          x1={t.x1}
          y1={t.y1}
          x2={t.x2}
          y2={t.y2}
          stroke="currentColor"
          strokeWidth="1"
          opacity="0.55"
        />
      ))}
      <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <circle cx="24" cy="24" r="16" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        d="M16.5 24.5 L21.5 29.5 L32 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
