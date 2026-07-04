"use client";

import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { appConfig, workspaceUrl } from "@/config/app.config";
import { useMe } from "@/lib/api/hooks";
import { HeroDemo } from "@/components/marketing/hero-demo";
import { MemoryField } from "@/components/brand/memory-field";
import { Reveal, Rule, TypeSet } from "@/components/motion";

// the fine fractal grain — same noise as the global .grain, but scoped to the
// stage so it adds depth here without the page-wide fixed overlay
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E\")";

/**
 * The opening stage. Theme-aware: in dark it is "the deep" — a green-black
 * field lit from within; in light, a sunlit conservatory on warm paper.
 * The atmosphere comes from the .stage tokens in theme.config.ts, lifted here
 * by a scoped grain and the breathing memory field behind the live proof.
 */
export function MarketingHero() {
  const { data: user } = useMe();
  return (
    // force the dark "deep" stage regardless of page theme — a cinematic band on
    // the light page; the landing header floats fixed and transparent over it
    // (scroll-aware), so pt-16 absorbs the header's height
    <section className="stage dark relative isolate overflow-hidden pt-16 text-foreground">
      {/* scoped grain — texture on the stage, no page-wide overlay */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-[0.05] mix-blend-overlay dark:opacity-[0.08]"
        style={{ backgroundImage: GRAIN }}
      />

      {/* the memory field — the brand's living archive, breathing behind the proof */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-36 top-1/2 -z-10 hidden w-[50rem] max-w-none -translate-y-1/2 opacity-50 sm:block lg:-right-16"
      >
        <MemoryField />
      </div>

      <div className="mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-12 sm:pt-16 lg:grid-cols-[0.95fr_1.05fr] lg:gap-14 lg:pb-20">
        {/* the pitch — left, editorial, specific */}
        <div className="max-w-xl">
          {/* items-start + a cap-height nudge: when the eyebrow wraps to two
              lines (390), the dot hangs on the FIRST line, not the block's middle */}
          <p className="tag-label inline-flex items-start gap-2 text-primary">
            <span className="mt-[0.3em] size-1.5 shrink-0 animate-pulse-dot rounded-full bg-primary" aria-hidden />
            <TypeSet immediate>Workflow automation for freelancers &amp; agencies</TypeSet>
          </p>
          <Rule immediate className="mt-3 max-w-[15rem]" delay={0.15} />

          <h1 className="display mt-6 text-[2.7rem] leading-[0.92] sm:text-[3.6rem] lg:text-[4.1rem]">
            <TypeSet as="div" immediate>
              Hand off the legwork.
            </TypeSet>
            {/* no mask on this line — the glow needs room to breathe */}
            <Reveal immediate delay={0.12} y={14}>
              Keep the <span className="glow-word">judgment.</span>
            </Reveal>
          </h1>

          <Reveal immediate delay={0.28}>
            <p className="mt-6 max-w-md text-[15px] leading-relaxed text-muted-foreground">
              Hand Clannon a brief and a team of specialist agents runs the whole
              job in parallel — research, analysis, drafting. Every claim is checked
              against its source before it reaches you, and each run sharpens the
              memory behind the next one.
            </p>
          </Reveal>

          <Reveal immediate delay={0.38}>
            {/* keyed so the anon→authed CTA swap reads as a fade, not a flash */}
            <div
              key={user ? "authed" : "anon"}
              className="mt-7 flex animate-fade-in flex-col gap-3 sm:flex-row sm:items-center"
            >
              {user ? (
                <ButtonLink href={workspaceUrl()} size="lg" className="w-full sm:w-auto">
                  Open workspace
                  <ArrowRight className="size-4" aria-hidden />
                </ButtonLink>
              ) : (
                <ButtonLink href="/signup" size="lg" className="w-full sm:w-auto">
                  Start free
                  <ArrowRight className="size-4" aria-hidden />
                </ButtonLink>
              )}
              {/* secondary action: a left-aligned link on mobile (not a second
                  full-width slab that mirrors the primary), a ghost button on
                  wider screens where they sit side by side */}
              <ButtonLink
                href={appConfig.features.demo ? "/demo" : "/login"}
                size="lg"
                variant="ghost"
                className="-ml-3 w-fit sm:ml-0 sm:w-auto"
              >
                See a real run
                <ArrowRight className="size-4 opacity-70" aria-hidden />
              </ButtonLink>
            </div>
            <p className="mt-5 text-[13px] text-faint">
              {user
                ? "Welcome back — pick up where you left off."
                : "No card required. Episodic memory is free, forever."}
            </p>
          </Reveal>
        </div>

        {/* the product, mid-run — the proof, floating in glass on the stage */}
        <Reveal immediate delay={0.18} className="min-w-0">
          <div className="glass rounded-2xl p-1.5 shadow-2xl shadow-black/50 ring-1 ring-white/10 sm:p-2">
            <HeroDemo />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
