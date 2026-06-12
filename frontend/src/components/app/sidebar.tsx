"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getClient } from "@/lib/api";
import { LogOut } from "lucide-react";
import { Mark } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/theme";
import { siteConfig } from "@/config/site.config";
import { APP_NAV as NAV } from "@/config/nav.config";
import { useEffectivePlan, useMe, useUsage } from "@/lib/api/hooks";
import { cn, formatTokens } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();
  const { data: user } = useMe();
  const { data: usage } = useUsage();
  const currentPlan = useEffectivePlan(user?.plan);

  const isActive = (item: (typeof NAV)[number]) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href);

  const pct = usage ? Math.min(100, Math.round((usage.used / usage.budget) * 100)) : 0;

  return (
    <>
      {/* desktop rail */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface md:flex">
        <Link
          href="/app"
          className="flex items-center gap-2.5 px-5 py-5"
          aria-label={`${siteConfig.name} workspace`}
        >
          <Mark className="size-6 text-primary" />
          <span className="font-display text-lg font-medium tracking-tight">{siteConfig.name}</span>
        </Link>

        <button
          type="button"
          onClick={() =>
            window.dispatchEvent(
              new KeyboardEvent("keydown", { key: "k", metaKey: true }),
            )
          }
          className="mx-3 mb-2 flex cursor-pointer items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-[13px] text-faint transition-colors hover:border-border-strong hover:text-muted-foreground"
        >
          Quick actions
          <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[10.5px]">⌘K</kbd>
        </button>

        <nav className="flex flex-1 flex-col gap-1 px-3" aria-label="Workspace">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(item) ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                isActive(item)
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <item.icon className="size-4" aria-hidden />
              {item.label}
            </Link>
          ))}
        </nav>

        {usage && user && (
          <div className="mx-3 mb-3 rounded-md border border-border bg-background p-3.5">
            <div className="flex items-center justify-between">
              <span className="tag-label text-faint">{currentPlan?.name}</span>
              <span className="text-[12px] text-muted-foreground tabular">
                {formatTokens(usage.used)} / {formatTokens(usage.budget)}
              </span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Token budget used"
              className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-muted"
            >
              <div
                className={cn(
                  "h-full rounded-full transition-[width] duration-500",
                  pct > 90 ? "bg-destructive" : pct > 75 ? "bg-memory" : "bg-primary",
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-1 border-t border-border px-5 py-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium capitalize">{user?.name}</p>
            <p className="truncate text-[12px] text-faint">{user?.email}</p>
          </div>
          <div className="flex shrink-0 items-center">
            <ThemeToggle />
            <button
              type="button"
              onClick={async () => {
                // end the session, then hard-navigate: the full reload
                // resets all client state and the auth guard can't race
                // us to /login
                await getClient().logout();
                window.location.assign("/");
              }}
              aria-label="Sign out"
              className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              <LogOut className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* mobile top bar + bottom nav */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-4 backdrop-blur-md md:hidden">
        <Link href="/app" className="flex items-center gap-2" aria-label={`${siteConfig.name} workspace`}>
          <Mark className="size-5 text-primary" />
          <span className="font-display text-base font-medium">{siteConfig.name}</span>
        </Link>
        <div className="flex items-center gap-1.5">
          {usage && (
            <span className="text-[12px] text-muted-foreground tabular">
              {formatTokens(usage.used)} / {formatTokens(usage.budget)}
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>
      <nav
        aria-label="Workspace"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      >
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(item) ? "page" : undefined}
            className={cn(
              "flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px]",
              isActive(item) ? "text-primary" : "text-faint",
            )}
          >
            <item.icon className="size-5" aria-hidden />
            {item.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
