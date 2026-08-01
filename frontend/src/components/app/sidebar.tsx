"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { getClient } from "@/lib/api";
import {
  BarChart3,
  ChevronsUpDown,
  CirclePlus,
  CreditCard,
  LogOut,
  Menu,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import { Mark } from "@/components/brand/logo";
import { openCommandPalette } from "@/components/app/command-palette";
import { menuKeyboardHandler, useFocusTrap, useScrollLock } from "@/lib/focus";
import { ThemeToggle } from "@/components/theme";
import { Button, ButtonLink } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { InfoTip } from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/toast";
import { siteConfig } from "@/config/site.config";
import { APP_NAV as NAV } from "@/config/nav.config";
import {
  useBudgetExhausted,
  useDeleteSession,
  useEffectivePlan,
  useMe,
  useRuns,
  useUsage,
} from "@/lib/api/hooks";
import { ProjectSwitcher } from "@/components/app/project-switcher";
import { useCurrentProjectId } from "@/components/app/project-provider";
import { groupBySession, type SessionEntry } from "@/lib/sessions";
import { cn, formatTokens } from "@/lib/utils";

// the sections under New chat / Search. The new-chat home gets its own button,
// and Settings lives inside the account menu (like ChatGPT/Claude).
const SECTIONS = NAV.filter(
  (item) => item.href !== "/app" && item.href !== "/app/settings",
);

/**
 * The rail's interior — New chat, Search, sections, the full conversation
 * history, plan/usage, account. Rendered in TWO places: the fixed desktop rail
 * and the mobile slide-in drawer, so the layout is identical to what people
 * already know from other AI apps; only the theme differs. `onNavigate` lets the
 * drawer close itself when something is tapped.
 */
function RailBody({
  onNavigate,
  onRequestDelete,
  onCollapse,
}: {
  onNavigate?: () => void;
  onRequestDelete?: (session: SessionEntry) => void;
  /** Desktop only — collapses the rail. Absent in the mobile drawer. */
  onCollapse?: () => void;
}) {
  const pathname = usePathname();
  const { data: user } = useMe();
  const { data: usage } = useUsage();
  const projectId = useCurrentProjectId();
  const { data: runs } = useRuns(projectId);
  const currentPlan = useEffectivePlan(user?.plan);
  const sessions = useMemo(() => groupBySession(runs), [runs]);

  const pct = usage ? Math.min(100, Math.round((usage.used / usage.budget) * 100)) : 0;
  const remaining = usage ? Math.max(0, usage.budget - usage.used) : 0;
  const exhausted = useBudgetExhausted();
  const resetDate = usage
    ? new Date(usage.periodEnd).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : "";

  // per-conversation "⋯" menu — fixed-positioned (anchored to the clicked dots)
  // so the scrolling history list can't clip it
  const [rowMenu, setRowMenu] = useState<{ session: SessionEntry; x: number; y: number } | null>(null);
  const rowMenuRef = useRef<HTMLDivElement>(null);
  // the kebab that opened the menu — Escape hands focus back to it
  const rowMenuAnchorRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!rowMenu) return;
    // DOM focus only (no state writes) — menus start on their first item
    rowMenuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const close = () => setRowMenu(null);
    const onDown = (e: PointerEvent) => {
      const t = e.target as Element;
      if (rowMenuRef.current?.contains(t) || t.closest("[data-row-kebab]")) return;
      close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      close();
      rowMenuAnchorRef.current?.focus();
    };
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    // a fixed menu detaches from its anchor on scroll — close it
    window.addEventListener("scroll", close, { capture: true });
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, { capture: true });
    };
  }, [rowMenu]);

  // the account menu — a popover holding Settings, Usage, Billing, theme, log out
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    // DOM focus only (no state writes) — menus start on their first item
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onDown = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setMenuOpen(false);
      menuTriggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const closeMenu = () => {
    setMenuOpen(false);
    onNavigate?.();
  };
  async function logout() {
    // end the session, then hard-navigate: the full reload resets all client
    // state and the auth guard can't race us to /login
    await getClient().logout();
    window.location.assign("/");
  }
  const menuItem =
    "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground";

  return (
    <>
      <div className="flex items-center justify-between gap-1 px-3 py-4">
        <Link
          href="/app"
          onClick={onNavigate}
          className="flex items-center gap-2.5 px-2"
          aria-label={`${siteConfig.name} workspace`}
        >
          <Mark className="size-6 text-primary" />
          <span className="font-display text-lg font-medium tracking-tight">{siteConfig.name}</span>
        </Link>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="hidden size-8 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground md:flex"
          >
            <PanelLeftClose className="size-4" aria-hidden />
          </button>
        )}
      </div>

      {/* project switcher — scopes history, the home, and memory to one client */}
      <ProjectSwitcher onNavigate={onNavigate} />

      {/* New chat — the primary action, first thing, like ChatGPT/Claude */}
      <Link
        href="/app"
        onClick={onNavigate}
        className="mx-3 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
      >
        <CirclePlus className="size-[18px] text-primary" aria-hidden />
        New chat
      </Link>

      <button
        type="button"
        onClick={() => {
          onNavigate?.();
          openCommandPalette();
        }}
        className="mx-3 mt-1 flex items-center justify-between rounded-md px-3 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <span className="flex items-center gap-2.5">
          <Search className="size-4" aria-hidden />
          Search
        </span>
        <kbd className="hidden rounded border border-border px-1.5 py-0.5 font-mono text-[11px] md:block">
          ⌘K
        </kbd>
      </button>

      <nav className="mt-1 flex flex-col gap-0.5 px-3" aria-label="Sections">
        {SECTIONS.map((item) => {
          const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary-soft font-medium text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <item.icon className="size-4" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* conversation history — the bulk of the rail, like every chat app */}
      <div className="mt-5 flex min-h-0 flex-1 flex-col">
        <p className="tag-label px-5 pb-1.5 text-faint">Recent</p>
        {sessions.length === 0 ? (
          <p className="px-5 text-[12px] leading-relaxed text-faint">
            Your conversations show up here.
          </p>
        ) : (
          <ul className="flex-1 space-y-px overflow-y-auto px-3 pb-2">
            {sessions.map((session) => {
              const active = pathname === `/app/runs/${session.latestId}`;
              return (
                <li key={session.sessionId} className="group relative">
                  <Link
                    href={`/app/runs/${session.latestId}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={session.title}
                    // the morph source — this row expands into the run page's
                    // brief bubble. Only when NOT active: the sidebar persists
                    // across navigation, so the active row must drop the name
                    // or it would collide with the run page's matching element.
                    style={
                      active
                        ? undefined
                        : { viewTransitionName: `run-open-${session.latestId.replace(/[^a-zA-Z0-9]/g, "-")}` }
                    }
                    className={cn(
                      "block rounded-md py-1.5 pl-3 pr-9 text-[13px] transition-colors",
                      active
                        ? "bg-primary-soft font-medium text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {/* §11.3: fade out, never a mid-word "…" — the fade must sit on
                        the text's own box (inside pr-9), not the padded link edge */}
                    <span className="truncate-fade block">{session.title}</span>
                  </Link>
                  {/* the "⋯" actions menu — revealed on hover (PC); always
                      tappable at the right edge on mobile (the drawer is below md) */}
                  <button
                    type="button"
                    data-row-kebab
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const r = e.currentTarget.getBoundingClientRect();
                      rowMenuAnchorRef.current = e.currentTarget;
                      setRowMenu((cur) =>
                        cur?.session.sessionId === session.sessionId
                          ? null
                          : { session, x: r.right, y: r.bottom },
                      );
                    }}
                    aria-label={`Actions for “${session.title}”`}
                    aria-haspopup="menu"
                    aria-expanded={rowMenu?.session.sessionId === session.sessionId}
                    className={cn(
                      "absolute right-1 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded text-faint transition-colors hover:bg-muted hover:text-foreground",
                      rowMenu?.session.sessionId === session.sessionId
                        ? "opacity-100"
                        : "opacity-100 md:opacity-0 md:transition-opacity md:group-hover:opacity-100 md:focus-within:opacity-100",
                    )}
                  >
                    <MoreHorizontal className="size-4" aria-hidden />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* the "⋯" menu — fixed so the scrolling history can't clip it */}
      {rowMenu && (
        <div
          ref={rowMenuRef}
          role="menu"
          // ref is still null while this render is committing — read it at event time
          onKeyDown={(e) => menuKeyboardHandler(e.currentTarget)(e)}
          style={{ position: "fixed", top: rowMenu.y + 4, left: rowMenu.x }}
          className="z-[60] min-w-[8.5rem] -translate-x-full overflow-hidden rounded-md border border-border bg-surface-raised p-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              const s = rowMenu.session;
              setRowMenu(null);
              onRequestDelete?.(s);
            }}
            className="flex w-full items-center gap-2.5 rounded px-2.5 py-1.5 text-[13px] text-destructive transition-colors hover:bg-destructive-soft"
          >
            <Trash2 className="size-3.5" aria-hidden />
            Delete
          </button>
        </div>
      )}

      {usage && user && (
        <div
          className={cn(
            "mx-3 mb-3 rounded-md border p-3.5",
            exhausted ? "border-destructive/40 bg-destructive-soft" : "border-border bg-background",
          )}
        >
          <div className="flex items-center justify-between">
            <span className="tag-label text-faint">{currentPlan?.name}</span>
            <span className="flex items-center gap-1">
              <span className={cn("text-[12px] tabular", exhausted ? "text-destructive" : "text-muted-foreground")}>
                {formatTokens(usage.used)} / {formatTokens(usage.budget)}
              </span>
              <InfoTip
                align="end"
                label="Your monthly token budget. A run stops cleanly at the limit — you're never charged mid-run."
              />
            </span>
          </div>

          {exhausted ? (
            /* the budget-exhausted state (UI_SPEC §1, §13) — blocking, but calm:
               work pauses, nothing is lost, and the way forward is one tap away */
            <>
              <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
                You&apos;re out of tokens this period. Work pauses cleanly — nothing is
                lost. Resets {resetDate}.
              </p>
              <ButtonLink
                href="/app/settings?tab=billing"
                size="sm"
                onClick={onNavigate}
                className="mt-2.5 w-full"
              >
                Upgrade to continue
              </ButtonLink>
            </>
          ) : (
            <>
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
              {/* a sentence, not a column — tabular here would slot-space the
                  decimal point ("5 . 4M") */}
              <p
                className={cn(
                  "mt-2 text-[11px]",
                  pct > 90 ? "text-memory" : "text-faint",
                )}
              >
                {formatTokens(remaining)} left · resets {resetDate}
              </p>
            </>
          )}
        </div>
      )}

      <div ref={menuRef} className="relative border-t border-border p-2">
        {menuOpen && (
          <div
            role="menu"
            // read the element at event time — refs are off-limits in render
            onKeyDown={(e) => menuKeyboardHandler(e.currentTarget)(e)}
            className="absolute inset-x-2 bottom-full mb-1 z-10 overflow-hidden rounded-lg border border-border bg-surface-raised p-1 shadow-xl"
          >
            <p className="truncate px-3 py-1.5 text-[12px] text-faint">{user?.email}</p>
            <div className="my-1 h-px bg-border" />
            <Link href="/app/settings?tab=account" onClick={closeMenu} role="menuitem" className={menuItem}>
              <Settings className="size-4 text-faint" aria-hidden /> Settings
            </Link>
            <Link href="/app/settings?tab=usage" onClick={closeMenu} role="menuitem" className={menuItem}>
              <BarChart3 className="size-4 text-faint" aria-hidden /> Usage
            </Link>
            <Link href="/app/settings?tab=billing" onClick={closeMenu} role="menuitem" className={menuItem}>
              <CreditCard className="size-4 text-faint" aria-hidden /> Billing
            </Link>
            <div className="my-1 h-px bg-border" />
            <div className="flex items-center justify-between gap-2 px-3 py-1.5 text-sm text-muted-foreground">
              <span>Theme</span>
              <ThemeToggle />
            </div>
            <div className="my-1 h-px bg-border" />
            <button type="button" onClick={logout} role="menuitem" className={cn(menuItem, "text-destructive hover:text-destructive")}>
              <LogOut className="size-4" aria-hidden /> Log out
            </button>
          </div>
        )}
        <button
          ref={menuTriggerRef}
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted"
        >
          <span
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[13px] font-semibold uppercase text-primary"
            aria-hidden
          >
            {user?.name?.trim()?.[0] ?? "?"}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium capitalize">{user?.name}</p>
            <p className="truncate text-[12px] text-faint">
              {currentPlan?.name ? `${currentPlan.name} plan` : user?.email}
            </p>
          </div>
          <ChevronsUpDown className="size-4 shrink-0 text-faint" aria-hidden />
        </button>
      </div>
    </>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const del = useDeleteSession();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<SessionEntry | null>(null);

  function deleteSession() {
    const session = confirmDelete;
    if (!session) return;
    del.mutate(session.sessionId, {
      onSuccess: () => {
        setConfirmDelete(null);
        toast({ title: "Conversation deleted", tone: "success" });
        // if you were viewing this conversation, drop back to the workspace
        if (pathname === `/app/runs/${session.latestId}`) router.push("/app");
      },
    });
  }

  // close the drawer whenever the route changes (a backstop to the per-link
  // onNavigate close) — render-time reset, no effect needed
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    setDrawerOpen(false);
  }

  // trap focus in the drawer while it's open (restores to the hamburger on
  // close), lock the background scroll, and close on Escape
  const drawerRef = useRef<HTMLElement>(null);
  useFocusTrap(drawerOpen, drawerRef);
  useScrollLock(drawerOpen);
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <>
      {/* floating reopen handle — shown only while the rail is collapsed (desktop) */}
      {collapsed && (
        <button
          type="button"
          onClick={onToggle}
          aria-label="Open sidebar"
          title="Open sidebar"
          className="fixed left-3 top-3 z-40 hidden size-9 cursor-pointer items-center justify-center rounded-md border border-border bg-surface/90 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:text-foreground md:flex"
        >
          <PanelLeftOpen className="size-4" aria-hidden />
        </button>
      )}

      {/* desktop rail */}
      <aside
        className={cn(
          // dark: the rail recedes BELOW the canvas (stage step) so the work is
          // the lit plane — the elevation ladder, spent
          "fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface dark:bg-stage md:flex",
          collapsed && "md:hidden",
        )}
      >
        <RailBody onRequestDelete={setConfirmDelete} onCollapse={onToggle} />
      </aside>

      {/* mobile top bar — hamburger + brand, with New chat as the primary action */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-3 backdrop-blur-md md:hidden">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open menu"
            className="flex size-10 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Menu className="size-5" aria-hidden />
          </button>
          <Link href="/app" className="flex items-center gap-2" aria-label={`${siteConfig.name} workspace`}>
            <Mark className="size-5 text-primary" />
            <span className="font-display text-base font-medium">{siteConfig.name}</span>
          </Link>
        </div>
        <div className="flex items-center gap-1">
          <Link
            href="/app"
            aria-label="New chat"
            className="flex size-10 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <SquarePen className="size-5" aria-hidden />
          </Link>
          <ThemeToggle />
        </div>
      </header>

      {/* mobile slide-in drawer — the full rail (New chat + search + history + account) */}
      <div
        className={cn("fixed inset-0 z-50 md:hidden", !drawerOpen && "pointer-events-none")}
        aria-hidden={!drawerOpen}
      >
        <button
          type="button"
          tabIndex={drawerOpen ? 0 : -1}
          aria-label="Close menu"
          onClick={() => setDrawerOpen(false)}
          className={cn(
            "absolute inset-0 cursor-default bg-black/50 transition-opacity duration-300",
            drawerOpen ? "opacity-100" : "opacity-0",
          )}
        />
        <aside
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-label="Menu"
          className={cn(
            "absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col border-r border-border bg-surface shadow-xl transition-transform duration-300 ease-out",
            drawerOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            aria-label="Close menu"
            className="absolute right-2 top-3.5 z-10 flex size-9 items-center justify-center rounded-md text-faint hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
          <RailBody onNavigate={() => setDrawerOpen(false)} onRequestDelete={setConfirmDelete} />
        </aside>
      </div>

      {/* confirm deleting a whole conversation */}
      <Dialog
        open={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        title="Delete this conversation?"
      >
        {confirmDelete && (
          <div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              “{confirmDelete.title}” and all {confirmDelete.turnCount}{" "}
              {confirmDelete.turnCount === 1 ? "turn" : "turns"} in it will be
              permanently removed. This can&apos;t be undone.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
                Keep it
              </Button>
              <Button variant="destructive" loading={del.isPending} onClick={deleteSession}>
                Delete
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </>
  );
}
