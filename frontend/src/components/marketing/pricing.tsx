"use client";

import { Check } from "lucide-react";
import { useEffectivePlans, useMe } from "@/lib/api/hooks";
import { ButtonLink } from "@/components/ui/button";
import { SectionHeading } from "@/components/marketing/section-heading";
import { Stagger, StaggerItem } from "@/components/motion";
import { formatTokens } from "@/lib/utils";

export function PricingSection() {
  // backend-defined plans when available, plans.ts otherwise
  const PLANS = useEffectivePlans();
  // signed-in visitors manage plans in the workspace, not via signup
  const { data: user } = useMe();
  return (
    <section id="pricing" className="mx-auto max-w-6xl px-5 py-20 sm:py-28">
      <SectionHeading
        kicker="Pricing"
        intro="Every plan is a monthly token budget you spend however you like — three deep teardowns or thirty quick briefs. A typical client research task that takes a freelancer 6–10 hours runs in about 20 minutes."
      >
        Priced by what it does, not how often you ask.
      </SectionHeading>

      {/* the rate card — one ledger, columns struck by hairlines, no floating cards */}
      <Stagger className="mt-12 grid grid-cols-1 gap-px overflow-hidden border border-border bg-border md:grid-cols-2 xl:grid-cols-4">
        {PLANS.map((plan) => (
          <StaggerItem
            key={plan.id}
            className="relative flex h-full flex-col bg-surface p-6"
          >
            {/* the chosen column wears a struck rule, like a ledger's ruled total */}
            {plan.highlight && (
              <span className="absolute inset-x-0 top-0 h-[3px] bg-primary" aria-hidden />
            )}
            <div className="flex items-center justify-between">
              <h3 className="tag-label text-muted-foreground">{plan.name}</h3>
              {plan.highlight && (
                <span className="tag-label rounded-full bg-memory-soft px-2.5 py-1 text-memory">
                  Most useful
                </span>
              )}
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
                href={user ? "/app/settings?tab=billing" : "/signup"}
                variant={plan.highlight ? "primary" : "outline"}
                className="w-full"
              >
                {user
                  ? plan.id === user.plan
                    ? "Your current plan"
                    : `Switch in the app`
                  : plan.monthlyUsd === 0
                    ? "Start free"
                    : `Start with ${plan.name}`}
              </ButtonLink>
            </div>
          </StaggerItem>
        ))}
      </Stagger>

      <p className="mt-8 text-center text-[13px] text-faint">
        Memory tiers unlock progressively — episodic memory is included on every
        plan, free forever. Cancel anytime; your wiki exports as plain markdown.
      </p>
    </section>
  );
}
