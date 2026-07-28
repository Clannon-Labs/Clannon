import { Check } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { SectionHeading } from "@/components/marketing/section-heading";
import { formatTokens } from "@/lib/utils";
import { getPublicPlans } from "@/lib/public-plans";

export async function PricingSection() {
  const plans = await getPublicPlans();
  return (
    <section id="pricing" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 sm:py-28">
      <SectionHeading
        kicker="Pricing"
        intro="Every plan is a monthly token budget you spend however you like — three deep teardowns or thirty quick briefs. A typical client research task that takes a freelancer 6–10 hours runs in about 20 minutes."
      >
        Priced by what it does, not how often you ask.
      </SectionHeading>

      {/* the rate card — one ledger, columns struck by hairlines, no floating cards */}
      <div className="mt-12 grid grid-cols-1 gap-px overflow-hidden border border-border bg-border md:grid-cols-2 xl:grid-cols-4">
        {plans.map((plan) => {
          // signed in: your actual plan is the marked one; signed out: the free
          // tier is where everyone starts
          const isCurrent = plan.monthlyUsd === 0;
          const struck = isCurrent || plan.highlight;
          return (
          <article
            key={plan.id}
            className="relative flex h-full flex-col bg-surface p-6"
          >
            {/* the chosen column wears a struck rule, like a ledger's ruled total */}
            {struck && (
              <span className="absolute inset-x-0 top-0 h-[3px] bg-primary" aria-hidden />
            )}
            <div className="flex items-center justify-between">
              <h3 className="tag-label text-muted-foreground">{plan.name}</h3>
              {isCurrent ? (
                <span className="tag-label rounded-full bg-primary-soft px-2.5 py-1 text-primary">
                  You&apos;re here
                </span>
              ) : plan.highlight ? (
                <span className="tag-label rounded-full bg-memory-soft px-2.5 py-1 text-memory">
                  Most useful
                </span>
              ) : null}
            </div>

            <div className="mt-5 flex items-baseline gap-1.5">
              <span className="display text-[3rem] leading-none tabular">
                ${plan.monthlyUsd}
              </span>
              <span className="text-sm text-muted-foreground">/mo</span>
            </div>
            <p className="mt-2 text-[13px] text-faint tabular">
              {formatTokens(plan.tokenBudget)} tokens / month
            </p>

            <p className="mt-4 min-h-10 text-sm leading-relaxed text-muted-foreground">
              {plan.tagline}
            </p>

            <ul className="mt-5 flex flex-col gap-2.5">
              {plan.features.map((feature) => (
                <li key={feature} className="flex items-start gap-2.5 text-sm">
                  <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                  <span className="text-muted-foreground">{feature}</span>
                </li>
              ))}
            </ul>

            <div className="mt-auto pt-6">
              <ButtonLink
                href="/signup"
                prefetch={false}
                variant={struck ? "primary" : "outline"}
                className="w-full"
              >
                {plan.monthlyUsd === 0 ? "Start free" : `Start with ${plan.name}`}
              </ButtonLink>
            </div>
          </article>
          );
        })}
      </div>

      <p className="mt-8 text-center text-[13px] text-faint">
        Memory tiers unlock progressively — episodic memory is included on every
        plan, free forever. Cancel anytime; your wiki exports as plain markdown.
      </p>
    </section>
  );
}
