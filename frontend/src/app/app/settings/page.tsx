"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  useMe,
  useModelConfig,
  useSetModelLayer,
  useUsage,
} from "@/lib/api/hooks";
import { ModelRoleList, prettyModel } from "@/components/app/model-picker";
import { UsageSummaryPanel } from "@/components/app/usage-summary";
import { BillingSettings } from "@/components/app/billing-settings";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ThemeSegment } from "@/components/theme";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useNotifyPreference } from "@/lib/notify-preference";

function UsageChart() {
  const { data: usage } = useUsage();
  if (!usage) return <Skeleton className="h-48" />;
  return <UsageSummaryPanel usage={usage} />;
}

function ModelsTab() {
  const { data: layers } = useModelConfig();
  const setLayer = useSetModelLayer();
  const toast = useToast();

  if (!layers) return <Skeleton className="h-64" />;

  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
        Pick a model per role — these are your workspace defaults, applied to every new
        run. Defaults are best-for-task, and you can still override per run from the
        composer. The security roles — verifier and output filter — are system-managed
        and can&apos;t be swapped.
      </p>
      <ModelRoleList
        layers={layers}
        valueFor={(l) => l.model}
        pending={setLayer.isPending}
        onSelect={(l, model) =>
          setLayer.mutate(
            { layer: l.layer, model },
            {
              onSuccess: () =>
                toast({
                  title: `${l.label} model updated`,
                  description: `New runs use ${prettyModel(model)} for ${l.label.toLowerCase()}.`,
                  tone: "success",
                }),
            },
          )
        }
      />
    </div>
  );
}

/** Runs can take minutes — this is "tell me when it's done" for the run
 *  you're on when you tab away, not a general activity feed. Off by default:
 *  the browser gates the permission prompt behind a real click, so there's
 *  no version of this that can be silently on. */
function NotificationSetting() {
  const { enabled, permission, requestEnable, disable } = useNotifyPreference();
  const toast = useToast();

  if (permission === null) {
    return (
      <p className="text-[13px] leading-relaxed text-faint">
        Your browser doesn&apos;t support notifications.
      </p>
    );
  }

  async function toggle(next: boolean) {
    if (!next) {
      disable();
      return;
    }
    const granted = await requestEnable();
    if (!granted) {
      toast({
        title: "Notifications blocked",
        description: "Your browser didn't grant permission — check its site settings for Clannon.",
        tone: "warning",
      });
    }
  }

  return (
    <div className="mt-3 flex items-start justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3.5">
      <div>
        <p className="text-[13px] font-medium text-foreground">Notify me when a run finishes</p>
        <p className="mt-1 max-w-sm text-[12px] leading-relaxed text-muted-foreground">
          Only fires for a run you have open in a background tab — come back to a
          finished report without watching for it.
        </p>
        {enabled && permission === "denied" && (
          <p className="mt-1.5 text-[12px] text-warning">
            Blocked in your browser — enable notifications for this site to use it.
          </p>
        )}
      </div>
      <Switch
        checked={enabled && permission === "granted"}
        onCheckedChange={toggle}
        label="Notify me when a run finishes"
      />
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
        <TabsList className="scrollbar-none max-w-full overflow-x-auto">
          <TabsTrigger value="account">Account</TabsTrigger>
          <TabsTrigger value="models">Models</TabsTrigger>
          <TabsTrigger value="usage">Usage</TabsTrigger>
          <TabsTrigger value="billing">Billing</TabsTrigger>
        </TabsList>

        <TabsContent value="account" className="mt-6">
          <div className="flex max-w-md flex-col gap-5">
            {/* read-only on purpose: an editable-looking form with a dead save
                button is a lie. This becomes a real form when accounts go live. */}
            <dl className="divide-y divide-border/60 rounded-lg border border-border bg-surface px-5">
              <div className="grid grid-cols-[6rem_1fr] items-baseline gap-3 py-3.5">
                <dt className="tag-label text-faint">Name</dt>
                <dd className="truncate text-sm font-medium capitalize text-foreground">{user?.name ?? "—"}</dd>
              </div>
              <div className="grid grid-cols-[6rem_1fr] items-baseline gap-3 py-3.5">
                <dt className="tag-label text-faint">Email</dt>
                <dd className="truncate text-sm text-foreground">{user?.email ?? "—"}</dd>
              </div>
            </dl>
            <p className="text-[12px] leading-relaxed text-faint">
              Name and email editing arrive with cloud accounts — changes will
              need <span className="whitespace-nowrap">re-verification</span>.
            </p>

            <dl className="divide-y divide-border/60 rounded-lg border border-border bg-surface px-5">
              <div className="grid grid-cols-[6rem_1fr] items-baseline gap-3 py-3.5">
                <dt className="tag-label text-faint">Plan</dt>
                <dd className="text-sm font-medium capitalize text-foreground">{user?.plan ?? "—"}</dd>
              </div>
              <div className="grid grid-cols-[6rem_1fr] items-baseline gap-3 py-3.5">
                <dt className="tag-label text-faint">Workspace</dt>
                <dd className="truncate text-sm text-foreground">Personal</dd>
              </div>
            </dl>

            <div className="mt-2 border-t border-border pt-5">
              <p className="text-sm font-medium">Appearance</p>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                Light, dark, or follow your operating system.
              </p>
              <ThemeSegment className="mt-3" />
            </div>

            <div className="border-t border-border pt-5">
              <p className="text-sm font-medium">Notifications</p>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                Get pinged the moment a long-running run wraps up.
              </p>
              <NotificationSetting />
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
          <BillingSettings />
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
