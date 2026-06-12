"use client";

import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { appConfig } from "@/config/app.config";
import { HeroDemo } from "@/components/marketing/hero-demo";
import { MemoryField } from "@/components/brand/memory-field";
import { Reveal, Rule, TypeSet } from "@/components/motion";

/**
 * The opening stage. Theme-aware: in dark it is "the deep" — a green-black
 * field lit from within; in light, a sunlit conservatory on warm paper.
 * The atmosphere comes entirely from the .stage tokens in theme.config.ts.
 */
export function MarketingHero() {
  return (
    <section className="stage hairline-b relative isolate overflow-hidden text-foreground">
      {/* the memory field — the brand's living archive, breathing behind the proof */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 top-1/2 -z-10 hidden w-[46rem] max-w-none -translate-y-1/2 opacity-40 sm:block lg:-right-24"
      >
        <MemoryField />
      </div>

      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-16 sm:pt-24 lg:grid-cols-[0.95fr_1.05fr] lg:gap-14 lg:pb-28">
        {/* the pitch — left, editorial, specific */}
        <div className="max-w-xl">
          <p className="tag-label text-primary">
            <TypeSet immediate>Research automation for freelancers and small agencies</TypeSet>
          </p>
          <Rule immediate className="mt-3 max-w-[15rem]" delay={0.15} />

          <h1 className="display mt-7 text-[2.9rem] sm:text-[4rem] lg:text-[4.5rem]">
            <TypeSet as="div" immediate>
              Hand off the research.
            </TypeSet>
            {/* no mask on this line — the glow needs room to breathe */}
            <Reveal immediate delay={0.12} y={14}>
              Keep the <span className="glow-word">judgment.</span>
            </Reveal>
          </h1>

          <Reveal immediate delay={0.28}>
            <p className="mt-7 max-w-md text-[16px] leading-relaxed text-muted-foreground">
              Give Clannon a client brief and a team of specialist agents
              researches it in parallel. Every claim is checked against its
              source before it reaches you — and each run sharpens the memory
              behind the next one.
            </p>
          </Reveal>

          <Reveal immediate delay={0.38}>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <ButtonLink href="/signup" size="lg" className="w-full sm:w-auto">
                Start free
                <ArrowRight className="size-4" aria-hidden />
              </ButtonLink>
              <ButtonLink
                href={appConfig.features.demo ? "#demo" : "/login"}
                size="lg"
                variant="ghost"
                className="w-full sm:w-auto"
              >
                See a real run
              </ButtonLink>
            </div>
            <p className="mt-5 text-[13px] text-faint">
              No card required. Episodic memory is free, forever.
            </p>
          </Reveal>
        </div>

        {/* the product, mid-run — the proof, floating in glass on the stage */}
        <Reveal immediate delay={0.18} className="min-w-0">
          <div className="glass rounded-2xl p-1.5 shadow-2xl shadow-black/25 sm:p-2">
            <HeroDemo />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
