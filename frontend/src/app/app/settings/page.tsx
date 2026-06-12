"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import type { PlanId } from "@/config/plans";
import { Check, ChevronRight, Cpu, ShieldCheck } from "lucide-react";
import {
  useEffectivePlan,
  useEffectivePlans,
  useMe,
  useModelConfig,
  useStartCheckout,
  useSetModelLayer,
  useUsage,
} from "@/lib/api/hooks";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ThemeSegment } from "@/components/theme";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn, formatTokens } from "@/lib/utils";

function UsageChart() {
  const { data: usage } = useUsage();
  if (!usage) return <Skeleton className="h-48" />;

  const max = Math.max(...usage.byDay.map((d) => d.tokens), 1);
  const pct = Math.min(100, Math.round((usage.used / usage.budget) * 100));

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Billing period {usage.periodStart} → {usage.periodEnd}
          </p>
          <p className="text-sm tabular">
            <span className="font-semibold text-foreground">{formatTokens(usage.used)}</span>
            <span className="text-faint"> of {formatTokens(usage.budget)} tokens</span>
          </p>
        </div>
        <div
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Token budget used this period"
          className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-700",
              pct > 90 ? "bg-destructive" : pct > 75 ? "bg-memory" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-2 text-[12.5px] text-faint">
          Budgets are enforced atomically per call — runs stop cleanly at the
          limit, never mid-charge.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <h3 className="tag-label text-muted-foreground">Daily spend — last 14 days</h3>
        <div className="mt-4 flex h-36 items-end gap-1.5" aria-hidden>
          {usage.byDay.map((day) => (
            <div key={day.date} className="group relative flex-1">
              <div
                className="w-full rounded-t-sm bg-primary/70 transition-colors group-hover:bg-primary"
                style={{ height: `${Math.max(4, (day.tokens / max) * 128)}px` }}
              />
              <span className="pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded border border-border bg-surface-raised px-1.5 py-0.5 text-[10.5px] tabular group-hover:block">
                {formatTokens(day.tokens)}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex justify-between text-[10.5px] text-faint tabular">
          <span>{usage.byDay[0]?.date.slice(5)}</span>
          <span>{usage.byDay.at(-1)?.date.slice(5)}</span>
        </div>
        <p className="sr-only">
          Daily token usage for the last 14 days, totalling {formatTokens(usage.used)}.
        </p>
      </div>
    </div>
  );
}

function ModelsTab() {
  const { data: layers } = useModelConfig();
  const setLayer = useSetModelLayer();
  const toast = useToast();

  if (!layers) return <Skeleton className="h-64" />;

  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
        The reasoning layers are yours to configure. The security layers —
        verifier and output filter — are system-managed: their models are part
        of the pipeline&apos;s safety guarantee and can&apos;t be swapped.
      </p>
      {layers.map((layer) => (
        <div
          key={layer.layer}
          className="rounded-lg border border-border bg-surface p-5"
        >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[15px] font-semibold">
              {layer.locked ? (
                <ShieldCheck className="size-4 text-memory" aria-hidden />
              ) : (
                <Cpu className="size-4 text-primary" aria-hidden />
              )}
              {layer.label}
              {layer.locked && (
                <span className="tag-label rounded-full bg-memory-soft px-2 py-0.5 text-memory">
                  System managed
                </span>
              )}
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {layer.description}
            </p>
          </div>
          {layer.locked ? (
            <p className="shrink-0 rounded-md border border-border bg-background px-3 py-2.5 font-mono text-[13px] text-muted-foreground">
              {layer.model}
            </p>
          ) : (
          <div className="shrink-0">
            <label className="sr-only" htmlFor={`model-${layer.layer}`}>
              Model for {layer.label}
            </label>
            <select
              id={`model-${layer.layer}`}
              value={layer.model}
              disabled={setLayer.isPending}
              onChange={(e) =>
                setLayer.mutate(
                  { layer: layer.layer, model: e.target.value },
                  {
                    onSuccess: () =>
                      toast({
                        title: `${layer.label} model updated`,
                        description: `Next runs use ${e.target.value}.`,
                        tone: "success",
                      }),
                  },
                )
              }
              className="h-10 cursor-pointer rounded-md border border-border-strong bg-surface-raised px-3 font-mono text-[13px] text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25"
            >
              {layer.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          )}
        </div>

        {/* per-expert overrides, tucked away until wanted */}
        {layer.experts && layer.experts.length > 0 && (
          <details className="group mt-4 border-t border-border pt-3">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
              <ChevronRight
                className="size-3.5 transition-transform duration-200 group-open:rotate-90"
                aria-hidden
              />
              Per-expert overrides
              <span className="text-faint">— each expert can run its own model</span>
            </summary>
            <div className="mt-3 flex flex-col gap-2.5">
              {layer.experts.map((expert) => (
                <div
                  key={expert.key}
                  className="flex flex-col gap-2 rounded-md bg-background px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <p className="font-mono text-[13px]">
                    {expert.key}
                    <span className="ml-2 font-sans text-faint">{expert.label}</span>
                  </p>
                  <div>
                    <label className="sr-only" htmlFor={`model-expert-${expert.key}`}>
                      Model for {expert.label}
                    </label>
                    <select
                      id={`model-expert-${expert.key}`}
                      value={expert.model}
                      disabled={setLayer.isPending}
                      onChange={(e) =>
                        setLayer.mutate(
                          { layer: `expert:${expert.key}`, model: e.target.value },
                          {
                            onSuccess: () =>
                              toast({
                                title: `${expert.label} model updated`,
                                description: `Next runs use ${e.target.value} for this expert.`,
                                tone: "success",
                              }),
                          },
                        )
                      }
                      className="h-9 cursor-pointer rounded-md border border-border-strong bg-surface-raised px-2.5 font-mono text-[12.5px] text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25"
                    >
                      {layer.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </details>
        )}
        </div>
      ))}
    </div>
  );
}

function BillingTab() {
  const { data: user } = useMe();
  const PLANS = useEffectivePlans();
  const currentPlan = useEffectivePlan(user?.plan);
  const checkout = useStartCheckout();
  const toast = useToast();
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);

  function changePlan(planId: PlanId, planName: string, isUpgrade: boolean) {
    setPendingPlan(planId);
    checkout.mutate(planId, {
      onSuccess: (res) => {
        setPendingPlan(null);
        // with a Stripe URL the browser is already navigating away
        if (!res.url) {
          toast({
            title: isUpgrade ? `Welcome to ${planName}` : `Switched to ${planName}`,
            description: isUpgrade
              ? "Your new budget and memory tiers are active now."
              : "The change applies — downgrades keep your paid period intact.",
            tone: "success",
          });
        }
      },
      onError: () => {
        setPendingPlan(null);
        toast({
          title: "Plan change failed",
          description: "Nothing was charged. Try again or contact support.",
          tone: "warning",
        });
      },
    });
  }

  return (
    <div>
      <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
        You&apos;re on <span className="font-semibold text-foreground">{currentPlan?.name}</span>.
        Budgets reset on each billing date. Cancellation and refunds work the
        way the{" "}
        <Link
          href="/legal/refunds"
          className="text-primary underline underline-offset-2"
        >
          refund policy
        </Link>{" "}
        says they do — no fine print.
      </p>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === user?.plan;
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
                ${plan.monthlyUsd}
                <span className="font-sans text-sm text-muted-foreground">/mo</span>
              </p>
              <p className="mt-1 text-[12.5px] text-faint">
                {formatTokens(plan.tokenBudget)} tokens · {plan.memoryTiers.length}/4 memory tiers
              </p>
              {!isCurrent && (
                <Button
                  variant={plan.monthlyUsd > (currentPlan?.monthlyUsd ?? 0) ? "primary" : "outline"}
                  size="sm"
                  className="mt-4 w-full"
                  loading={pendingPlan === plan.id}
                  disabled={pendingPlan !== null}
                  onClick={() =>
                    changePlan(
                      plan.id,
                      plan.name,
                      plan.monthlyUsd > (currentPlan?.monthlyUsd ?? 0),
                    )
                  }
                >
                  {pendingPlan === plan.id
                    ? "Processing…"
                    : plan.monthlyUsd > (currentPlan?.monthlyUsd ?? 0)
                      ? `Upgrade to ${plan.name}`
                      : `Switch to ${plan.name}`}
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SettingsInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: user } = useMe();
  const tab = searchParams.get("tab") ?? "account";

  return (
    <div className="mx-auto max-w-4xl">
      <header>
        <p className="tag-label text-faint">Settings</p>
        <h1 className="display mt-3 text-[2.4rem] leading-[1.0]">
          Your setup
        </h1>
      </header>

      <Tabs
        defaultValue="account"
        value={tab}
        onValueChange={(v) => router.replace(`/app/settings?tab=${v}`, { scroll: false })}
        className="mt-8"
      >
        <TabsList className="max-w-full overflow-x-auto">
          <TabsTrigger value="account">Account</TabsTrigger>
          <TabsTrigger value="models">Models</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="billing">Billing</TabsTrigger>
        </TabsList>

        <TabsContent value="account" className="mt-6">
          <div className="flex max-w-md flex-col gap-5">
            <Input label="Name" defaultValue={user?.name ?? ""} autoComplete="name" className="capitalize" />
            <Input
              label="Email"
              type="email"
              defaultValue={user?.email ?? ""}
              autoComplete="email"
              disabled
              hint="Email changes require re-verification — available once accounts are live."
            />
            <div>
              <Button disabled>Save changes — soon</Button>
            </div>

            <div className="mt-2 border-t border-border pt-5">
              <p className="text-sm font-medium">Appearance</p>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                Light, dark, or follow your operating system.
              </p>
              <ThemeSegment className="mt-3" />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="models" className="mt-6">
          <ModelsTab />
        </TabsContent>

        <TabsContent value="usage" className="mt-6">
          <UsageChart />
        </TabsContent>

        <TabsContent value="billing" className="mt-6">
          <BillingTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-4xl" />}>
      <SettingsInner />
    </Suspense>
  );
}
