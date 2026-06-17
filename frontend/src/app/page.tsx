import { ArrowRight, Eye, Network, BookOpenCheck } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { appConfig } from "@/config/app.config";
import { MarketingHeader } from "@/components/marketing/header";
import { MarketingHero } from "@/components/marketing/hero";
import { LiveDemo } from "@/components/marketing/live-demo";
import { Reveal, Stagger, StaggerItem, Rule } from "@/components/motion";
import { PipelineSection } from "@/components/marketing/pipeline";
import { MemorySection } from "@/components/marketing/memory-section";
import { PricingSection } from "@/components/marketing/pricing";
import { FaqSection } from "@/components/marketing/faq";
import { MarketingFooter } from "@/components/marketing/footer";

const PILLARS = [
  {
    icon: Eye,
    title: "Glass box, not black box",
    body: "You watch every routing decision, every search, every conflict between sources — live, as the orchestrator makes them.",
  },
  {
    icon: Network,
    title: "Parallel, not patient",
    body: "Multi-domain questions get multiple specialists working at once. A six-hour research task comes back while you make coffee.",
  },
  {
    icon: BookOpenCheck,
    title: "Filtered, not hopeful",
    body: "Citations are checked against their sources before delivery. If a claim can't be grounded, it doesn't ship.",
  },
];

export default function LandingPage() {
  return (
    /* Theme follows the toggle (default: light — see public/theme.js). The
       hero and closing CTA are .stage surfaces and adapt to either theme. */
    <div className="bg-background text-foreground">
      <MarketingHeader />
      <main id="main">
        <MarketingHero />

        {/* ---------- pillars ---------- */}
        <section className="hairline-t bg-surface">
          <Stagger className="mx-auto grid max-w-6xl grid-cols-1 gap-px overflow-hidden border-y border-border bg-border sm:grid-cols-3">
            {PILLARS.map((pillar, i) => (
              <StaggerItem key={pillar.title} className="h-full bg-surface px-6 py-12 sm:px-8">
                <div className="flex items-center justify-between">
                  <pillar.icon className="size-5 text-primary" aria-hidden />
                  <span className="tag-label text-faint">0{i + 1}</span>
                </div>
                <h2 className="display-soft mt-6 text-[1.5rem] leading-none">{pillar.title}</h2>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {pillar.body}
                </p>
              </StaggerItem>
            ))}
          </Stagger>
        </section>

        {appConfig.features.demo && <LiveDemo />}
        <PipelineSection />
        <MemorySection />
        <PricingSection />
        <FaqSection />

        {/* ---------- final CTA — the closing stage, the dark bookend to the hero ---------- */}
        <section className="stage dark relative isolate overflow-hidden px-5 py-28 text-foreground sm:py-36">
          <Reveal className="mx-auto max-w-3xl text-center">
            <Rule className="mx-auto mb-10 max-w-[6rem]" />
            <h2 className="display mx-auto max-w-3xl text-balance text-[2.6rem] leading-[0.98] sm:text-[4.2rem]">
              The first run is good.
              <br />
              The tenth one <em className="glow-word not-italic">knows your clients.</em>
            </h2>
            <p className="mx-auto mt-6 max-w-md text-[15px] leading-relaxed text-muted-foreground">
              Start free. Run a real brief. Watch the decision log and decide for
              yourself.
            </p>
            <div className="mt-9 flex justify-center">
              <ButtonLink href="/signup" size="lg">
                Plant the first ring
                <ArrowRight className="size-4" aria-hidden />
              </ButtonLink>
            </div>
          </Reveal>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}

