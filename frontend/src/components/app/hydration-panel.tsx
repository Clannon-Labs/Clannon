"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronRight, Pencil, Sprout, X } from "lucide-react";
import { useDeleteMemory, useHydrationPreview, useMemoryEntries } from "@/lib/api/hooks";
import type { MemoryEntry } from "@/lib/api";
import { TIER_LABELS, type MemoryTier } from "@/config/plans";
import { MemoryRings } from "@/components/brand/memory-rings";
import { Rule } from "@/components/motion";
import { useToast } from "@/components/ui/toast";
import { cn, formatRelativeTime } from "@/lib/utils";

/* ---------------------------------------------------------------------------
   The Second-Session Moment (UI_SPEC §7) — "this component is the product."

   When a returning user opens a new chat, the Memory Manager's hydration
   surfaces PROACTIVELY, before they re-explain anything: colleague language,
   not a database dump; provenance on demand; every item one tap from corrected.
   Then it recedes to a one-line chip the instant work starts — it must never
   nag or dominate. Three states are designed: rich, sparse, and corrected-item.
--------------------------------------------------------------------------- */

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

const byRecency = (a: MemoryEntry, b: MemoryEntry) =>
  +new Date(b.updatedAt) - +new Date(a.updatedAt);

/** What to carry into a fresh session, before a word is typed — a curated
 *  recap, not a relevance dump: the client we're on, what happened last, how
 *  you like to work. Falls back to plain recency so it's robust to any data. */
function restingRecap(entries: MemoryEntry[]): MemoryEntry[] {
  const recent = [...entries].sort(byRecency);
  const pick: MemoryEntry[] = [];
  const take = (pred: (e: MemoryEntry) => boolean) => {
    const e = recent.find((x) => pred(x) && !pick.includes(x));
    if (e) pick.push(e);
  };
  take((e) => e.tier === "wiki" && /^client\b/i.test(e.title)); // who we're working for
  take((e) => e.tier === "episodic"); // what we did last
  take((e) => e.tier === "wiki"); // a standing instruction (style guide, facts)
  take((e) => e.tier === "procedural" || e.tier === "semantic"); // a habit or a learned fact
  for (const e of recent) {
    if (pick.length >= 4) break;
    if (!pick.includes(e)) pick.push(e);
  }
  return pick.slice(0, 4);
}

/** The one colleague line under the header — names the client if we know one,
 *  otherwise stays honest about what's being carried. */
function recapLine(entries: MemoryEntry[]): string {
  const client = entries.find((e) => e.tier === "wiki" && /^client\b/i.test(e.title));
  const name = client?.title.replace(/^client[:\s]*/i, "").split(/[—–-]/)[0].trim();
  if (name) return `Here's what I'm carrying on ${name}, and how you like to work — each one yours to correct.`;
  return "A few things I'm carrying from our last sessions — each one yours to correct.";
}

const TIER_TICK: Record<MemoryTier, string> = {
  wiki: "bg-memory",
  semantic: "bg-log-route",
  episodic: "bg-faint",
  procedural: "bg-log-expert",
};

/** Provenance in colleague language — why I know this, by tier. */
const TRUST_LINE: Record<MemoryTier, string> = {
  wiki: "You wrote this. It outranks everything I infer.",
  semantic: "I learned this and kept the source.",
  episodic: "From a past run on this work.",
  procedural: "A pattern I picked up across your runs.",
};

/** Confidence as a single-hue, three-step ramp (never red→green): low
 *  confidence reads as "uncertain," not "bad." */
function ConfidenceTicks({ value }: { value: number }) {
  const lit = value >= 0.8 ? 3 : value >= 0.55 ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-0.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span key={i} className={cn("h-2.5 w-1 rounded-full", i < lit ? "bg-primary" : "bg-border")} />
      ))}
    </span>
  );
}

function ProvRow({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-[4.5rem] shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-faint">{label}</dt>
      <dd className={cn("min-w-0 flex-1 text-muted-foreground", mono && "font-mono text-[11px]")}>{children}</dd>
    </div>
  );
}

function HydrationItem({
  entry,
  reduce,
  expanded,
  onToggle,
  onCorrect,
  stageDelay = 0,
}: {
  entry: MemoryEntry;
  reduce: boolean | null;
  expanded: boolean;
  onToggle: () => void;
  onCorrect: () => void;
  /** Seconds before this row prints — the recap assembles line by line. */
  stageDelay?: number;
}) {
  const isWiki = entry.tier === "wiki";
  return (
    <motion.li
      layout={!reduce}
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduce ? undefined : { opacity: 0, x: 10, height: 0, marginTop: 0 }}
      transition={{ duration: 0.32, delay: stageDelay }}
      style={reduce ? undefined : { animationDelay: `${stageDelay + 0.1}s` }}
      className={cn(
        "grid grid-cols-[auto_1fr] gap-3 rounded-sm border-t border-border/60 py-3 first:border-t-0",
        // each memory "burns in" as it arrives — the amber wash cooling off
        !reduce && "animate-ignite",
      )}
    >
      {/* pin the tick+label to the title's first line, not the block's center */}
      <span className="flex items-center gap-2 self-start pt-[3px]">
        <span
          className={cn("size-1.5 rounded-full", TIER_TICK[entry.tier], !reduce && "animate-tick-pulse")}
          style={reduce ? undefined : { animationDelay: `${stageDelay + 0.1}s` }}
          aria-hidden
        />
        <span className="tag-label w-[4.5rem] text-faint">
          {TIER_LABELS[entry.tier]}
        </span>
      </span>

      <div className="min-w-0">
        <p className="text-[13px] font-medium leading-snug text-foreground">{entry.title}</p>
        <p className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-muted-foreground">{entry.content}</p>

        {/* the two affordances the spec asks for: provenance on demand, and a
            one-tap correction. Inferred memory can be "outdated"; wiki is yours
            to edit. */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="inline-flex min-h-7 items-center gap-1 text-[12px] text-faint transition-colors hover:text-muted-foreground"
          >
            Why do I know this?
            <ChevronRight className={cn("size-3 transition-transform duration-200", expanded && "rotate-90")} aria-hidden />
          </button>
          {isWiki ? (
            <Link
              href="/app/memory"
              className="inline-flex min-h-7 items-center gap-1 text-[12px] text-faint transition-colors hover:text-foreground"
            >
              <Pencil className="size-3" aria-hidden /> Wrong — fix it
            </Link>
          ) : (
            <button
              type="button"
              onClick={onCorrect}
              className="inline-flex min-h-7 items-center gap-1 text-[12px] text-faint transition-colors hover:text-destructive"
            >
              <X className="size-3" aria-hidden /> That&apos;s outdated
            </button>
          )}
        </div>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={reduce ? false : { height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={reduce ? undefined : { height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              className="overflow-hidden"
            >
              <dl className="mt-2 flex flex-col gap-1 rounded-md border border-border bg-surface px-3 py-2.5 text-[12px]">
                <ProvRow label="Trust">
                  {TIER_LABELS[entry.tier]} — {TRUST_LINE[entry.tier]}
                </ProvRow>
                {entry.confidence != null && (
                  <ProvRow label="Confidence">
                    <span className="inline-flex items-center gap-1.5">
                      <ConfidenceTicks value={entry.confidence} />
                      <span className="tabular">{Math.round(entry.confidence * 100)}%</span>
                    </span>
                  </ProvRow>
                )}
                {entry.source && <ProvRow label="Source">{entry.source}</ProvRow>}
                {entry.runId && (
                  <ProvRow label="From run" mono>
                    {entry.runId}
                  </ProvRow>
                )}
                <ProvRow label="Updated">{formatRelativeTime(entry.updatedAt)}</ProvRow>
              </dl>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.li>
  );
}

/**
 * The hydration moment. Lives on the new-chat screen: rests as a colleague
 * recap, recedes to a chip the instant the user starts typing.
 */
export function HydrationPanel({
  brief,
  projectId,
  className,
}: {
  brief: string;
  projectId?: string;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const { data: entries } = useMemoryEntries(projectId);
  const remove = useDeleteMemory();
  const toast = useToast();

  const [expandedId, setExpandedId] = useState<string | null>(null);
  // Locally suppressed the instant the user corrects one, so the item animates
  // out immediately rather than waiting on the round-trip.
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const briefTokens = useMemo(() => tokens(brief), [brief]);
  const listening = briefTokens.length > 0;

  // hand the draft to the Manager's dry-run at a debounced cadence — the chip
  // reflects the REAL ranking a run would hydrate, not a local guess
  const [debouncedBrief, setDebouncedBrief] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedBrief(brief), 500);
    return () => window.clearTimeout(t);
  }, [brief]);
  const preview = useHydrationPreview(debouncedBrief, projectId);

  const live = useMemo(() => (entries ?? []).filter((e) => !dismissed.has(e.id)), [entries, dismissed]);

  // resting: a curated recap of what's carried into the session
  const surfaced = useMemo(() => (live.length === 0 ? [] : restingRecap(live)), [live]);
  // typing: the dry-run hits (render-only — learned-tier ids are synthetic)
  const previewHits = useMemo(
    () => (preview.data ?? []).filter((e) => !dismissed.has(e.id)),
    [preview.data, dismissed],
  );

  const activeTier = (listening ? previewHits[0]?.tier : surfaced[0]?.tier) ?? null;
  const matched = listening ? previewHits.length > 0 : surfaced.length > 0;

  // ring↔list connection: as each recap row lands, its tier's ring brightens
  // for a beat — the dial and the list are one instrument. Timed to the same
  // stagger the rows print with; skipped entirely under reduced motion.
  const [flashTier, setFlashTier] = useState<MemoryTier | null>(null);
  const surfacedKey = surfaced.map((e) => e.id).join("|");
  useEffect(() => {
    if (reduce || listening || surfaced.length === 0) return;
    const timers: number[] = [];
    surfaced.forEach((entry, i) => {
      const at = (0.12 + i * 0.14) * 1000 + 100;
      timers.push(window.setTimeout(() => setFlashTier(entry.tier), at));
      timers.push(window.setTimeout(() => setFlashTier(null), at + 450));
    });
    return () => timers.forEach((t) => window.clearTimeout(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by ids, not array identity
  }, [surfacedKey, listening, reduce]);
  // sparse: little to nothing remembered yet (early in a relationship).
  const sparse = !listening && surfaced.length === 0;

  function correct(entry: MemoryEntry) {
    setExpandedId((id) => (id === entry.id ? null : id));
    setDismissed((s) => new Set(s).add(entry.id)); // instant removal
    remove.mutate(entry.id, {
      onSuccess: () => toast({ title: "Got it. I won't bring that up again.", tone: "success" }),
      onError: () => {
        setDismissed((s) => {
          const n = new Set(s);
          n.delete(entry.id);
          return n;
        });
        toast({ title: "Couldn't update that — try again.", tone: "warning" });
      },
    });
  }

  if (!entries) return null; // memory still loading — say nothing rather than flash

  return (
    <section aria-label="Picking up where we left off" className={cn("relative", className)}>
      <AnimatePresence mode="wait" initial={false}>
        {listening ? (
          /* RECEDED — work has started; shrink to a quiet, live chip */
          <motion.div
            key="chip"
            initial={reduce ? false : { opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={reduce ? undefined : { type: "spring", stiffness: 420, damping: 34 }}
            className="mt-3"
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-1.5 text-[12px] text-muted-foreground">
              <Sprout className="size-3.5 text-memory" aria-hidden />
              <span>Picking up where we left off</span>
              <span className="text-faint" aria-hidden>·</span>
              {matched ? (
                <span className="flex items-center gap-1.5 tabular">
                  {activeTier && <span className={cn("size-1.5 rounded-full", TIER_TICK[activeTier])} aria-hidden />}
                  {previewHits.length} in reach
                </span>
              ) : (
                <span className="text-faint">
                  listening<span className="caret" />
                </span>
              )}
            </span>
          </motion.div>
        ) : (
          /* RESTING — the proactive colleague recap */
          <motion.div
            key="rest"
            layout={!reduce}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="mt-3 grid grid-cols-[1fr_auto] gap-6 sm:gap-10"
          >
            <div className="min-w-0">
              <p className="tag-label flex items-center gap-2 text-memory">
                <Sprout className="size-3.5" aria-hidden /> Picking up where we left off
              </p>
              <p className="mt-2 max-w-md text-[13px] leading-relaxed text-muted-foreground">
                {sparse
                  ? "First session on this project — I'll start remembering from here."
                  : recapLine(live)}
              </p>

              {sparse ? (
                /* the four tiers as empty slots — the shape of what will
                   accumulate, before anything has */
                <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2" aria-hidden>
                  {(Object.keys(TIER_LABELS) as MemoryTier[]).map((tier) => (
                    <span
                      key={tier}
                      className="tag-label inline-flex items-center gap-1.5 text-faint"
                    >
                      <span className="size-1.5 rounded-full border border-border-strong" />
                      {TIER_LABELS[tier]}
                    </span>
                  ))}
                </div>
              ) : (
                <>
                  <Rule className="mt-3" />
                  <ol className="mt-1 flex flex-col">
                    <AnimatePresence initial={false} mode="popLayout">
                      {surfaced.map((entry, i) => (
                        <HydrationItem
                          key={entry.id}
                          entry={entry}
                          reduce={reduce}
                          stageDelay={0.12 + i * 0.14}
                          expanded={expandedId === entry.id}
                          onToggle={() => setExpandedId((id) => (id === entry.id ? null : entry.id))}
                          onCorrect={() => correct(entry)}
                        />
                      ))}
                    </AnimatePresence>
                  </ol>
                </>
              )}
            </div>

            {/* the rings — the active tier burns amber */}
            <div className="hidden w-28 shrink-0 self-start sm:block lg:w-36">
              <MemoryRings active={activeTier} flash={flashTier} drawOnView />
              <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-faint">
                {sparse ? "4 tiers · empty" : activeTier ? `${TIER_LABELS[activeTier]} forward` : "4 tiers"}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
