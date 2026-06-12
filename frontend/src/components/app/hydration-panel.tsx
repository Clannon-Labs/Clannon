"use client";

import { useMemo } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemoryEntries } from "@/lib/api/hooks";
import type { MemoryEntry } from "@/lib/api";
import { TIER_LABELS, type MemoryTier } from "@/config/plans";
import { MemoryRings } from "@/components/brand/memory-rings";
import { Rule } from "@/components/motion";
import { cn, formatRelativeTime } from "@/lib/utils";

const STOP = new Set([
  "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "is",
  "are", "our", "their", "this", "that", "client", "research", "report", "brief",
]);

function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}

/** Light, honest relevance: keyword overlap. The real pipeline hydrates
 *  semantically — this preview just shows which context is in reach. */
function score(entry: MemoryEntry, brief: string[]): number {
  if (brief.length === 0) return entry.tier === "wiki" ? 2 : 0; // standing context
  const hay = `${entry.title} ${entry.content}`.toLowerCase();
  let s = 0;
  for (const t of brief) if (hay.includes(t)) s += 1;
  if (entry.tier === "wiki") s += 0.5; // wiki always slightly forward — it outranks
  return s;
}

const TIER_TICK: Record<MemoryTier, string> = {
  wiki: "bg-memory",
  semantic: "bg-log-route",
  episodic: "bg-faint",
  procedural: "bg-log-expert",
};

/**
 * The hydration moment — the product's signature gesture: context surfaces
 * while the brief is still being typed. The thread stub ties this panel to
 * the composer above it; every memory that newly surfaces arrives with an
 * amber ignition (animate-ignite) that settles as it takes its place.
 */
export function HydrationPanel({ brief, className }: { brief: string; className?: string }) {
  const reduce = useReducedMotion();
  const { data: entries } = useMemoryEntries();
  const briefTokens = useMemo(() => tokens(brief), [brief]);

  const surfaced = useMemo(() => {
    if (!entries) return [];
    return entries
      .map((e) => ({ e, s: score(e, briefTokens) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 4)
      .map((x) => x.e);
  }, [entries, briefTokens]);

  const activeTier = surfaced[0]?.tier ?? null;
  const listening = briefTokens.length > 0;
  const matched = listening && surfaced.length > 0;

  return (
    <section aria-label="Context already loaded" className={cn("relative", className)}>
      {/* the thread — this panel is fed by the composer above it */}
      <div aria-hidden className="ml-7 flex flex-col items-center">
        <span className="h-8 w-px bg-gradient-to-b from-border-strong to-border" />
        <span
          className={cn(
            "-mt-px size-[7px] rounded-full transition-colors duration-500",
            matched ? "animate-pulse-dot bg-memory" : "bg-border-strong",
          )}
        />
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto] gap-6 sm:gap-10">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="tag-label text-memory">
              {matched ? "Surfacing for this brief" : "Already in the room"}
            </p>
            <p className="text-[11px] text-faint tabular" aria-live="polite">
              {surfaced.length > 0
                ? `${surfaced.length} ${surfaced.length === 1 ? "memory" : "memories"} in reach`
                : listening
                  ? "listening…"
                  : "4 tiers standing by"}
            </p>
          </div>
          <Rule className="mt-2.5" />
          <p className="mt-3 max-w-sm text-[13px] leading-relaxed text-muted-foreground">
            Before you finish typing, this context is loading into the run — wiki
            facts outrank anything the system infers.
          </p>

          <ol className="mt-5 flex flex-col">
            <AnimatePresence initial={false} mode="popLayout">
              {surfaced.map((entry) => (
                <motion.li
                  key={entry.id}
                  layout={!reduce}
                  initial={reduce ? false : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduce ? undefined : { opacity: 0, y: -6 }}
                  transition={{ duration: 0.4 }}
                  className={cn(
                    "grid grid-cols-[auto_1fr] gap-3 rounded-sm border-t border-border/60 px-1.5 py-3 first:border-t-0",
                    "-mx-1.5", // ignition wash bleeds slightly past the text column
                    !reduce && "animate-ignite",
                  )}
                >
                  <span className="flex items-center gap-2 pt-px">
                    <span className={cn("size-1.5 rounded-full", TIER_TICK[entry.tier])} aria-hidden />
                    <span className="w-[4.5rem] font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">
                      {TIER_LABELS[entry.tier]}
                    </span>
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-foreground">{entry.title}</p>
                    <p className="mt-0.5 line-clamp-1 text-[12px] leading-snug text-muted-foreground">
                      {entry.content}
                    </p>
                    <p className="mt-1 flex items-center gap-2.5 text-[10.5px] text-faint tabular">
                      {entry.confidence != null && <span>conf {entry.confidence.toFixed(2)}</span>}
                      {entry.source && <span>· {entry.source}</span>}
                      <span>· {formatRelativeTime(entry.updatedAt)}</span>
                    </p>
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
            {listening && surfaced.length === 0 && (
              <li className="border-t border-border/60 py-3 font-mono text-[12px] text-faint">
                nothing in memory matches yet<span className="caret" />
              </li>
            )}
          </ol>
        </div>

        {/* the rings — the active tier burns amber as context surfaces */}
        <div className="hidden w-28 shrink-0 self-start sm:block lg:w-36">
          <MemoryRings active={activeTier} drawOnView />
          <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-faint">
            {activeTier ? `${TIER_LABELS[activeTier]} live` : "4 tiers"}
          </p>
        </div>
      </div>
    </section>
  );
}
