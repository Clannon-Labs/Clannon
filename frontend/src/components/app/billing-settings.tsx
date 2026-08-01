"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Check, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import type { PlanId } from "@/config/plans";
import { ApiError } from "@/lib/api";
import {
  queryKeys,
  useBillingPortal,
  useEffectivePlan,
  useEffectivePlans,
  useMe,
  useStartCheckout,
} from "@/lib/api/hooks";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { cn, formatTokens } from "@/lib/utils";

export function BillingSettings() {
  const { data: user } = useMe();
  const plans = useEffectivePlans();
  const currentPlan = useEffectivePlan(user?.plan);
  const checkout = useStartCheckout();
  const portal = useBillingPortal();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [pendingPlan, setPendingPlan] = useState<PlanId | null>(null);
  const [creditAmount, setCreditAmount] = useState("100000");
  const handledSettlements = useRef(new Set<string>());

  useEffect(() => {
    for (const item of portal.data?.checkouts ?? []) {
      if (item.status !== "confirmed" || handledSettlements.current.has(item.id)) continue;
      handledSettlements.current.add(item.id);
      queryClient.invalidateQueries({ queryKey: queryKeys.me });
      queryClient.invalidateQueries({ queryKey: queryKeys.usage });
      toast({
        title: item.kind === "upgrade" ? "Plan upgrade confirmed" : "Credits confirmed",
        description: "Account and current-period usage now reflect the settlement.",
        tone: "success",
      });
    }
  }, [portal.data?.checkouts, queryClient, toast]);

  function startUpgrade(planId: PlanId, planName: string) {
    setPendingPlan(planId);
    checkout.mutate(
      { kind: "upgrade", planId },
      {
        onSuccess: () => {
          setPendingPlan(null);
          toast({
            title: `${planName} checkout created`,
            description: "Pending operator confirmation. This page checks status automatically.",
            tone: "success",
          });
        },
        onError: (error) => {
          setPendingPlan(null);
          toast({
            title: "Could not create checkout",
            description: error instanceof ApiError ? error.message : "Try again.",
            tone: "warning",
          });
        },
      },
    );
  }

  function startAddOn(event: FormEvent) {
    event.preventDefault();
    const amount = Number(creditAmount);
    const max = portal.data?.maxAddOnCredits;
    if (!Number.isInteger(amount) || amount <= 0 || max === undefined || amount > max) {
      toast({
        title: "Choose a valid credit amount",
        description: max === undefined
          ? "Billing limits are still loading."
          : `Enter a whole number from 1 to ${formatTokens(max)}.`,
        tone: "warning",
      });
      return;
    }
    checkout.mutate(
      { kind: "add_on", creditAmount: amount },
      {
        onSuccess: () => toast({
          title: "Add-on checkout created",
          description: "Credits stay pending until operator confirmation, then join this period.",
          tone: "success",
        }),
        onError: (error) => toast({
          title: "Could not create checkout",
          description: error instanceof ApiError ? error.message : "Try again.",
          tone: "warning",
        }),
      },
    );
  }

  return (
    <div>
      <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
        You&apos;re on <span className="font-semibold text-foreground">{currentPlan?.name}</span>.
        Budgets reset on each fixed billing anniversary. Cancellation and refunds follow the{" "}
        <Link href="/legal/refunds" className="text-primary underline underline-offset-2">
          refund policy
        </Link>.
      </p>

      <form onSubmit={startAddOn} className="mt-5 rounded-lg border border-border bg-surface p-5">
        <h3 className="text-[15px] font-semibold">Add tokens this period</h3>
        <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
          Confirmed credits join your current period; pending checkouts do not change entitlement.
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label className="flex-1">
            <span className="sr-only">Add-on token credits</span>
            <input
              type="number"
              min={1}
              max={portal.data?.maxAddOnCredits}
              step={1}
              value={creditAmount}
              onChange={(event) => setCreditAmount(event.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm tabular outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </label>
          <Button type="submit" size="sm" loading={checkout.isPending && pendingPlan === null}>
            Create add-on checkout
          </Button>
        </div>
        {portal.data && (
          <p className="mt-2 text-[11px] text-faint">
            Maximum {formatTokens(portal.data.maxAddOnCredits)} credits per checkout.
          </p>
        )}
      </form>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {plans.map((plan) => {
          const isCurrent = plan.id === user?.plan;
          const isUpgrade = plan.tokenBudget > (currentPlan?.tokenBudget ?? 0) && plan.monthlyUsd > 0;
          return (
            <div
              key={plan.id}
              className={cn(
                "rounded-lg border p-5",
                isCurrent ? "border-primary bg-primary-soft/40" : "border-border bg-surface",
              )}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-[15px] font-semibold">{plan.name}</h3>
                {isCurrent && (
                  <span className="tag-label flex items-center gap-1 text-primary">
                    <Check className="size-3.5" aria-hidden /> Current
                  </span>
                )}
              </div>
              <p className="display-soft mt-2 text-2xl tabular">
                {plan.monthlyUsd === 0 ? "Free" : <>{`$${plan.monthlyUsd}`}<span className="font-sans text-sm text-muted-foreground">/mo</span></>}
              </p>
              <p className="mt-1 text-[12px] text-faint">
                {formatTokens(plan.tokenBudget)} tokens · <span className="tabular">{plan.memoryTiers.length}/4</span> memory tiers
              </p>
              {isCurrent ? (
                <p className="mt-4 flex h-8 items-center justify-center rounded-md border border-primary/30 text-[12px] text-primary">
                  Your plan
                </p>
              ) : isUpgrade ? (
                <Button
                  size="sm"
                  className="mt-4 w-full"
                  loading={pendingPlan === plan.id}
                  disabled={checkout.isPending}
                  onClick={() => startUpgrade(plan.id, plan.name)}
                >
                  Upgrade to {plan.name}
                </Button>
              ) : (
                <p className="mt-4 flex h-8 items-center justify-center text-center text-[12px] text-faint">
                  Downgrades are not available through mock checkout
                </p>
              )}
            </div>
          );
        })}
      </div>

      <section className="mt-6" aria-labelledby="checkout-history-title">
        <div className="flex items-center justify-between gap-3">
          <h3 id="checkout-history-title" className="tag-label text-muted-foreground">Checkout status</h3>
          <Button variant="ghost" size="sm" onClick={() => portal.refetch()} loading={portal.isFetching}>
            <RefreshCw className="size-3.5" aria-hidden /> Refresh
          </Button>
        </div>
        {portal.data?.checkouts.length ? (
          <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface px-4">
            {portal.data.checkouts.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
                <span className="text-muted-foreground">
                  {item.kind === "upgrade" ? `Upgrade to ${item.planId}` : `${formatTokens(item.creditAmount ?? 0)} add-on credits`}
                </span>
                <span className={cn(
                  "tag-label",
                  item.status === "confirmed" ? "text-primary" : item.status === "failed" ? "text-destructive" : "text-memory",
                )}>
                  {item.status}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[12px] text-faint">No checkouts yet.</p>
        )}
      </section>
    </div>
  );
}
