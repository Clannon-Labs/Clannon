"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Check, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { planById, type PlanId } from "@/config/plans";
import { ApiError } from "@/lib/api";
import {
  queryKeys,
  useBillingPortal,
  useCancelSubscription,
  useDowngradePlan,
  useEffectivePlan,
  useEffectivePlans,
  useInvoices,
  useMe,
  useStartCheckout,
  useUndoCancelSubscription,
} from "@/lib/api/hooks";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { cn, formatTokens } from "@/lib/utils";

const dateLabel = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

const money = (cents: number) => (cents / 100).toLocaleString("en-US", { style: "currency", currency: "usd" });

export function BillingSettings() {
  const { data: user } = useMe();
  const plans = useEffectivePlans();
  const currentPlan = useEffectivePlan(user?.plan);
  const checkout = useStartCheckout();
  const portal = useBillingPortal();
  const invoices = useInvoices();
  const downgrade = useDowngradePlan();
  const cancelSub = useCancelSubscription();
  const undoCancelSub = useUndoCancelSubscription();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [pendingPlan, setPendingPlan] = useState<PlanId | null>(null);
  const [creditAmount, setCreditAmount] = useState("100000");
  const [confirmDowngrade, setConfirmDowngrade] = useState<PlanId | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
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

  function confirmDowngradePlan() {
    if (!confirmDowngrade) return;
    const planId = confirmDowngrade;
    downgrade.mutate(planId, {
      onSuccess: (result) => {
        setConfirmDowngrade(null);
        toast({
          title: `Moved to ${planById(result.newPlanId).name}`,
          description: "Your new budget applies immediately.",
          tone: "success",
        });
      },
      onError: (error) => {
        setConfirmDowngrade(null);
        toast({
          title: "Could not downgrade",
          description: error instanceof ApiError ? error.message : "Try again.",
          tone: "warning",
        });
      },
    });
  }

  function confirmCancelSubscription() {
    cancelSub.mutate(undefined, {
      onSuccess: (result) => {
        setConfirmCancel(false);
        toast({
          title: "Cancellation scheduled",
          description: result.cancelEffectiveAt
            ? `Your plan reverts to Free on ${dateLabel(result.cancelEffectiveAt)}. You keep full access until then.`
            : undefined,
          tone: "success",
        });
      },
      onError: (error) => {
        setConfirmCancel(false);
        toast({
          title: "Could not schedule cancellation",
          description: error instanceof ApiError ? error.message : "Try again.",
          tone: "warning",
        });
      },
    });
  }

  function keepPlan() {
    undoCancelSub.mutate(undefined, {
      onSuccess: () => toast({ title: "Cancellation undone", tone: "success" }),
    });
  }

  return (
    <div>
      <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
        You&apos;re on <span className="font-semibold text-foreground">{currentPlan?.name}</span>.
        Budgets reset on each fixed billing anniversary. Refunds follow the{" "}
        <Link href="/legal/refunds" className="text-primary underline underline-offset-2">
          refund policy
        </Link>.
      </p>

      {portal.data?.subscription.status === "cancel_scheduled" && portal.data.subscription.cancelEffectiveAt && (
        <div
          role="status"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-memory-soft px-4 py-3"
        >
          <p className="text-[13px] leading-relaxed text-memory">
            Your plan reverts to Free on{" "}
            <span className="font-semibold">{dateLabel(portal.data.subscription.cancelEffectiveAt)}</span>.
            You keep full access until then.
          </p>
          <Button variant="outline" size="sm" onClick={keepPlan} loading={undoCancelSub.isPending}>
            Keep my plan
          </Button>
        </div>
      )}

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
          // Free isn't offered here as a downgrade target — that's what
          // "Cancel subscription" below does (scheduled, at period end).
          // Downgrade is immediate and only moves between paid tiers, so
          // there's exactly one path to "go to Free," not two with
          // different timing semantics.
          const isDowngrade =
            plan.tokenBudget < (currentPlan?.tokenBudget ?? 0) && plan.monthlyUsd > 0;
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
              ) : isDowngrade ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4 w-full"
                  loading={downgrade.isPending && confirmDowngrade === plan.id}
                  disabled={downgrade.isPending}
                  onClick={() => setConfirmDowngrade(plan.id)}
                >
                  Move to {plan.name}
                </Button>
              ) : (
                <p className="mt-4 flex h-8 items-center justify-center text-center text-[12px] text-faint">
                  Cancel below to move here
                </p>
              )}
            </div>
          );
        })}
      </div>

      <section className="mt-6" aria-labelledby="invoices-title">
        <h3 id="invoices-title" className="tag-label text-muted-foreground">Invoices</h3>
        {invoices.data?.invoices.length ? (
          <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface px-4">
            {invoices.data.invoices.map((invoice) => (
              <li key={invoice.id} className="flex items-center justify-between gap-3 py-3 text-[12px]">
                <div>
                  <p className="text-foreground">{invoice.description}</p>
                  <p className="mt-0.5 text-faint">{dateLabel(invoice.issuedAt)}</p>
                </div>
                <span className="tabular text-muted-foreground">{money(invoice.amountCents)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[12px] text-faint">
            Nothing billed yet — invoices appear here once a plan or add-on purchase settles.
          </p>
        )}
      </section>

      <section className="mt-6" aria-labelledby="checkout-history-title">
        <div className="flex items-center justify-between gap-3">
          <h3 id="checkout-history-title" className="tag-label text-muted-foreground">Checkout status</h3>
          <Button variant="ghost" size="sm" onClick={() => portal.refetch()} loading={portal.isFetching}>
            <RefreshCw className="size-3.5" aria-hidden /> Refresh
          </Button>
        </div>
        <p className="mt-1 text-[11px] text-faint">
          Every checkout you started, pending or settled — not the same as the invoices above.
        </p>
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

      {currentPlan && currentPlan.monthlyUsd > 0 && portal.data?.subscription.status === "active" && (
        <section className="mt-6 rounded-lg border border-border bg-surface p-5" aria-labelledby="cancel-title">
          <h3 id="cancel-title" className="text-[15px] font-semibold">Cancel subscription</h3>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            You keep {currentPlan.name} and full access through the end of this billing period,
            then revert to the free plan. No partial-period refund — see the{" "}
            <Link href="/legal/refunds" className="text-primary underline underline-offset-2">
              refund policy
            </Link>.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => setConfirmCancel(true)}
          >
            Cancel subscription
          </Button>
        </section>
      )}

      <Dialog
        open={confirmDowngrade !== null}
        onClose={() => setConfirmDowngrade(null)}
        title={confirmDowngrade ? `Move to ${planById(confirmDowngrade).name}?` : ""}
      >
        {confirmDowngrade && (
          <div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Your budget changes to {formatTokens(planById(confirmDowngrade).tokenBudget)}{" "}
              tokens immediately. If this period&apos;s usage already exceeds that, the move is
              blocked until next period.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setConfirmDowngrade(null)}>
                Stay on {currentPlan?.name}
              </Button>
              <Button loading={downgrade.isPending} onClick={confirmDowngradePlan}>
                Move to {planById(confirmDowngrade).name}
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog
        open={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        title="Cancel your subscription?"
      >
        <div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            You keep {currentPlan?.name} and full access through the end of this billing period.
            After that, your account reverts to the free plan. You can undo this any time before
            then.
          </p>
          <div className="mt-5 flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setConfirmCancel(false)}>
              Keep my plan
            </Button>
            <Button variant="destructive" loading={cancelSub.isPending} onClick={confirmCancelSubscription}>
              Cancel subscription
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
