import { cn } from "@/lib/utils";

/**
 * The Memory Field — Clannon's signature image: a cross-section of a living
 * archive. Deliberately calm. The rings are still; the only motion is a soft
 * heartbeat at the core. No blur filters, no orbiting parts — restraint reads
 * as confidence, and it stays buttery under the hero's cursor parallax.
 */

const RINGS = [
  { r: 38, op: 0.5, dash: "", rot: 0 },
  { r: 62, op: 0.46, dash: "150 40", rot: -35 },
  { r: 88, op: 0.4, dash: "320 70", rot: 60 },
  { r: 116, op: 0.32, dash: "240 120", rot: 150 },
  { r: 146, op: 0.24, dash: "500 90", rot: 210 },
  { r: 178, op: 0.16, dash: "360 180", rot: 20 },
  { r: 212, op: 0.1, dash: "700 140", rot: 280 },
];

export function MemoryField({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 500 500" className={cn("size-full", className)} aria-hidden role="presentation">
      <defs>
        {/* soft glow built from a gradient, not a filter — costs nothing to paint */}
        <radialGradient id="mf-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--memory)" stopOpacity="0.5" />
          <stop offset="45%" stopColor="var(--memory)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--memory)" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="mf-core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--memory)" />
          <stop offset="100%" stopColor="var(--primary)" />
        </radialGradient>
      </defs>

      {/* still rings — drawn once, never re-painted */}
      <g>
        {RINGS.map((ring) => (
          <circle
            key={ring.r}
            cx="250"
            cy="250"
            r={ring.r}
            fill="none"
            stroke="var(--primary)"
            strokeWidth="1.25"
            strokeLinecap="round"
            strokeOpacity={ring.op}
            strokeDasharray={ring.dash || undefined}
            transform={`rotate(${ring.rot} 250 250)`}
          />
        ))}
      </g>

      {/* Static on marketing boot: Motion runtime costs more than this ambient
          heartbeat contributes to comprehension. Live product moments retain
          their motion. */}
      <circle
        cx="250"
        cy="250"
        r="120"
        fill="url(#mf-halo)"
        opacity="0.82"
      />
      <circle cx="250" cy="250" r="6.5" fill="url(#mf-core)" />
    </svg>
  );
}
