"use client";

import { motion, useReducedMotion } from "motion/react";
import type { MemoryTier } from "@/config/plans";
import { cn } from "@/lib/utils";
import { EASE } from "@/components/motion";

/** Outer rings were laid down first (highest trust); the core is the newest growth. */
const RINGS: { tier: MemoryTier; r: number }[] = [
  { tier: "wiki", r: 96 },
  { tier: "semantic", r: 76 },
  { tier: "episodic", r: 52 },
  { tier: "procedural", r: 28 },
];

/**
 * Concentric growth rings — the brand's load-bearing image: memory is a tree,
 * each tier a season laid down. Rings draw themselves on view; the active tier
 * burns amber. Used by the marketing memory section and the workspace
 * hydration panel, so the metaphor reads the same in both places.
 */
export function MemoryRings({
  active,
  className,
  drawOnView = true,
}: {
  active?: MemoryTier | null;
  className?: string;
  drawOnView?: boolean;
}) {
  const reduce = useReducedMotion();
  return (
    <svg viewBox="0 0 200 200" className={cn("size-full", className)} aria-hidden>
      {RINGS.map(({ tier, r }, i) => {
        const isActive = active === tier;
        return (
          <motion.circle
            key={tier}
            cx="100"
            cy="100"
            r={r}
            fill="none"
            strokeWidth={isActive ? 3.5 : 1.25}
            className={cn(
              "transition-[stroke-width,opacity] duration-500",
              isActive ? "text-memory opacity-100" : "text-border-strong opacity-70",
            )}
            stroke="currentColor"
            initial={reduce || !drawOnView ? false : { pathLength: 0, opacity: 0 }}
            whileInView={drawOnView ? { pathLength: 1, opacity: isActive ? 1 : 0.7 } : undefined}
            animate={drawOnView ? undefined : { pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.1, ease: EASE, delay: i * 0.14 }}
            style={{ rotate: -90, transformOrigin: "center" }}
          />
        );
      })}
      {/* the core — newest growth, always amber */}
      <motion.circle
        cx="100"
        cy="100"
        r="4"
        className="fill-memory"
        initial={reduce ? false : { scale: 0 }}
        whileInView={{ scale: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5, ease: EASE, delay: 0.6 }}
        style={{ transformOrigin: "center" }}
      />
    </svg>
  );
}
