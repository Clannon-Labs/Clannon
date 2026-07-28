import type { MemoryTier } from "@/config/plans";

const RINGS: { tier: MemoryTier; r: number }[] = [
  { tier: "wiki", r: 96 },
  { tier: "semantic", r: 76 },
  { tier: "episodic", r: 52 },
  { tier: "procedural", r: 28 },
];

const TIERS: { tier: MemoryTier; name: string; trust: string; description: string }[] = [
  {
    tier: "wiki",
    name: "Wiki",
    trust: "Highest trust",
    description:
      "Your editable source of truth. Client facts, style guides, preferences — written by you, and it outranks everything the system infers.",
  },
  {
    tier: "semantic",
    name: "Semantic",
    trust: "Source-backed",
    description:
      "Facts and relationships Clannon learns from your runs, each with provenance and a confidence score you can inspect.",
  },
  {
    tier: "episodic",
    name: "Episodic",
    trust: "Every plan",
    description:
      "What happened: past runs, decisions, outcomes, failed approaches. The baseline that makes continuity possible — included free.",
  },
  {
    tier: "procedural",
    name: "Procedural",
    trust: "How you work",
    description:
      "Your habits, formats, and recurring patterns. The tenth report follows your conventions without being told.",
  },
];

/**
 * CSS :has() links focused/hovered tier cards to their trust rings. Same
 * interaction, no React state or hydration for an offscreen marketing section.
 */
export function MemorySection() {
  return (
    <section id="memory" className="hairline-t scroll-mt-20 bg-surface">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:py-28">
        <p className="tag-label text-memory">Memory — the part that compounds</p>
        <span aria-hidden className="mt-3 block h-px max-w-[28rem] bg-border" />

        <h2 className="mt-6 max-w-3xl text-balance text-4xl sm:text-[3.4rem]">
          <span className="display block leading-[0.96]">Tools forget you between sessions.</span>
          <span className="display mt-1 block leading-[0.96] text-primary">
            Clannon lays down rings.
          </span>
        </h2>

        <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
          Four memory tiers feed every run before planning even starts. By the
          third project with a client, you stop re-explaining — the context is
          already in the room.
        </p>

        <div className="memory-showcase mt-16 grid grid-cols-1 items-center gap-12 lg:grid-cols-[1fr_1.35fr] lg:gap-16">
          <div className="mx-auto w-56 sm:w-72 lg:w-full lg:max-w-sm">
            <svg viewBox="0 0 200 200" className="size-full" aria-hidden>
              {RINGS.map(({ tier, r }) => (
                <circle
                  key={tier}
                  cx="100"
                  cy="100"
                  r={r}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  className={`memory-ring memory-ring-${tier} text-ring-line`}
                />
              ))}
              <circle cx="100" cy="100" r="4" className="fill-memory" />
            </svg>
          </div>

          <div className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2">
            {TIERS.map((tier) => (
              <article
                key={tier.tier}
                data-memory-tier={tier.tier}
                tabIndex={0}
                className="group h-full cursor-default bg-background p-6 transition-colors duration-300 hover:bg-memory-soft/60 focus-visible:bg-memory-soft/60"
              >
                <div className="flex items-center justify-between">
                  <h3 className="display-soft text-[1.35rem] leading-none">{tier.name}</h3>
                  <span className="tag-label rounded-full bg-memory-soft px-2.5 py-1 text-memory transition-colors group-hover:bg-memory group-hover:text-primary-foreground group-focus-visible:bg-memory group-focus-visible:text-primary-foreground">
                    {tier.trust}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {tier.description}
                </p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
