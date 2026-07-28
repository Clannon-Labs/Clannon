import Link from "next/link";
import { ArrowRight, LineChart, Swords, TrendingUp, type LucideIcon } from "lucide-react";
import { DEMO_BRIEFS } from "@/config/demo.config";
import { ButtonLink } from "@/components/ui/button";
import { SectionHeading } from "@/components/marketing/section-heading";

const BRIEF_ICONS: LucideIcon[] = [TrendingUp, Swords, LineChart];

/**
 * The landing's demo teaser. The full experience is its own page (/demo) — a
 * chat exactly like the workspace, running a canned, isolated pipeline. This
 * section just frames it and routes you there; it never runs anything inline,
 * so there's a single source of truth for the demo.
 */
export function LiveDemo() {
  return (
    <section id="demo" className="hairline-t">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:py-28">
        <SectionHeading
          kicker="Live demo — no signup"
          intro="Pick a starter and watch a real run — the same decision log, parallel experts, and quality filter you get in the workspace. Canned and free; the real thing remembers."
        >
          Don&apos;t take our word for it. Watch a run.
        </SectionHeading>

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {DEMO_BRIEFS.map((brief, i) => {
            const Icon = BRIEF_ICONS[i] ?? TrendingUp;
            return (
              <Link
                key={brief.label}
                href="/demo"
                prefetch={false}
                className="group flex flex-col gap-3 rounded-xl border border-border bg-surface p-5 transition-colors hover:border-primary hover:bg-muted"
              >
                <Icon className="size-5 text-primary/70 transition-colors group-hover:text-primary" aria-hidden />
                <span className="text-[14px] font-medium leading-snug text-foreground">{brief.label}</span>
                <span className="mt-auto inline-flex items-center gap-1 text-[12px] text-faint transition-colors group-hover:text-primary">
                  Watch the run
                  <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </span>
              </Link>
            );
          })}
        </div>

        <div className="mt-8">
          <ButtonLink href="/demo" prefetch={false} size="lg">
            Open the live demo
            <ArrowRight className="size-4" aria-hidden />
          </ButtonLink>
        </div>
      </div>
    </section>
  );
}
