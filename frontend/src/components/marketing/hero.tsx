import { ArrowRight } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { appConfig } from "@/config/app.config";
import { HeroDemo } from "@/components/marketing/hero-demo";
import { MemoryField } from "@/components/brand/memory-field";

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
  return (
    // force the dark "deep" stage regardless of page theme — a cinematic band on
    // the light page, directly below the stable public navigation
    <section className="stage dark relative isolate overflow-hidden text-foreground">
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
            {/* nbsp-bind so "&" never ends a line at 390 */}
            <span>Workflow automation for freelancers&nbsp;&amp;&nbsp;agencies</span>
          </p>
          <span aria-hidden className="mt-3 block h-px max-w-[15rem] bg-border" />

          <h1 className="display mt-6 text-[2.7rem] leading-[0.92] sm:text-[3.6rem] lg:text-[4.1rem]">
            <span className="block">
              Hand off the legwork.
            </span>
            <span className="block">
              Keep the <span className="glow-word">judgment.</span>
            </span>
          </h1>

          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-muted-foreground">
            Hand Clannon a brief and a team of specialist agents runs the whole
            job in parallel — research, analysis, drafting. Every claim is checked
            against its source before it reaches you, and each run sharpens the
            memory behind the next one.
          </p>

          <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center">
            <ButtonLink href="/signup" prefetch={false} size="lg" className="w-full sm:w-auto">
              Start free
              <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
            <ButtonLink
              href={appConfig.features.demo ? "/demo" : "/login"}
              prefetch={false}
              size="lg"
              variant="ghost"
              className="-ml-3 w-fit sm:ml-0 sm:w-auto"
            >
              See a real run
              <ArrowRight className="size-4 opacity-70" aria-hidden />
            </ButtonLink>
          </div>
          <p className="mt-5 text-[13px] text-faint">
            No card required. Episodic memory is free, forever.
          </p>
        </div>

        {/* the product, mid-run — the proof, floating in glass on the stage */}
        <div className="min-w-0">
          <div className="glass rounded-2xl p-1.5 shadow-2xl shadow-black/50 ring-1 ring-white/10 sm:p-2">
            <HeroDemo />
          </div>
        </div>
      </div>
    </section>
  );
}
