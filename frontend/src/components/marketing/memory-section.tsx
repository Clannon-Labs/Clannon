"use client";

import { useState } from "react";
import type { MemoryTier } from "@/config/plans";
import { MemoryRings } from "@/components/brand/memory-rings";
import { Reveal, Stagger, StaggerItem, Rule, TypeSet } from "@/components/motion";
import { cn } from "@/lib/utils";

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

export function MemorySection() {
  // hover- and focus-driven, not auto-cycling — calmer, and the reader
  // controls it (keyboard included)
  const [active, setActive] = useState<MemoryTier | null>(null);

  return (
    <section id="memory" className="hairline-t scroll-mt-20 bg-surface">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:py-28">
        <p className="tag-label text-memory">Memory — the part that compounds</p>
        <Rule className="mt-3 max-w-[28rem]" />

        <h2 className="mt-6 max-w-3xl text-balance text-4xl sm:text-[3.4rem]">
          <span className="display block leading-[0.96]">
            <TypeSet>Tools forget you</TypeSet>{" "}
            <TypeSet delay={0.08}>between sessions.</TypeSet>
          </span>
          <span className="display mt-1 block leading-[0.96] text-primary">
            <TypeSet delay={0.18}>Clannon lays down rings.</TypeSet>
          </span>
        </h2>

        <Reveal delay={0.1}>
          <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            Four memory tiers feed every run before planning even starts. By the
            third project with a client, you stop re-explaining — the context is
            already in the room.
          </p>
        </Reveal>

        <div className="mt-16 grid grid-cols-1 items-center gap-12 lg:grid-cols-[1fr_1.35fr] lg:gap-16">
          <Reveal className="mx-auto w-56 sm:w-72 lg:w-full lg:max-w-sm" y={0}>
            <MemoryRings active={active} drawOnView />
          </Reveal>

          <div onMouseLeave={() => setActive(null)}>
          <Stagger className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2">
            {TIERS.map((tier) => (
              <StaggerItem key={tier.tier}>
                <div
                  tabIndex={0}
                  onMouseEnter={() => setActive(tier.tier)}
                  onFocus={() => setActive(tier.tier)}
                  onBlur={() => setActive(null)}
                  className={cn(
                    "h-full cursor-default bg-background p-6 transition-colors duration-300",
                    active === tier.tier && "bg-memory-soft/60",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <h3 className="display-soft text-[1.35rem] leading-none">{tier.name}</h3>
                    <span
                      className={cn(
                        "tag-label rounded-full px-2.5 py-1 transition-colors",
                        active === tier.tier
                          ? "bg-memory text-primary-foreground"
                          : "bg-memory-soft text-memory",
                      )}
                    >
                      {tier.trust}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                    {tier.description}
                  </p>
                </div>
              </StaggerItem>
            ))}
          </Stagger>
          </div>
        </div>
      </div>
    </section>
  );
}
