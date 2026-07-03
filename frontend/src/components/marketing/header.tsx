"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";
import { Wordmark } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme";
import { useMe } from "@/lib/api/hooks";
import { siteConfig } from "@/config/site.config";
import { MARKETING_NAV as NAV } from "@/config/nav.config";
import { workspaceUrl } from "@/config/app.config";
import { useFocusTrap, useScrollLock } from "@/lib/focus";
import { cn } from "@/lib/utils";

export function MarketingHeader() {
  const [open, setOpen] = useState(false);
  // already signed in? the whole site lets you slip straight into the workspace
  const { data: user } = useMe();
  // transparent (light-on-dark) over the hero, solid once scrolled past it
  const [scrolled, setScrolled] = useState(false);

  // keep focus (and scroll) inside the open panel; the trap hands focus back
  // to the toggle button on close
  const panelRef = useRef<HTMLElement>(null);
  useFocusTrap(open, panelRef);
  useScrollLock(open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // when open on mobile, the panel needs a solid backdrop even at the top
  const solid = scrolled || open;

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors duration-300",
        solid
          ? "border-b border-border bg-background/85 backdrop-blur-md"
          : "dark border-b border-transparent text-foreground",
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link href="/" aria-label={`${siteConfig.name} home`} className="shrink-0">
          <Wordmark />
        </Link>

        <nav className="hidden items-center gap-8 md:flex" aria-label="Main">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <ThemeToggle />
          {/* keyed so the anon→authed swap reads as a fade, not a flash */}
          <span key={user ? "authed" : "anon"} className="flex animate-fade-in items-center gap-3">
          {user ? (
            <ButtonLink href={workspaceUrl()} size="sm">
              Open workspace
              <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Sign in
              </Link>
              <ButtonLink href="/signup" size="sm">
                Start free
              </ButtonLink>
            </>
          )}
          </span>
        </div>

        <div className="flex items-center gap-1 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            className="flex size-11 cursor-pointer items-center justify-center rounded-md text-foreground"
            aria-expanded={open}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>

      {open && (
        <nav
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label="Mobile"
          className="animate-fade-in border-t border-border bg-background px-5 py-4 md:hidden"
        >
          <div className="flex flex-col gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-3 text-[15px] text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
            <div className="mt-3 flex items-center gap-3 border-t border-border pt-4">
              {user ? (
                <ButtonLink href={workspaceUrl()} className="flex-1">
                  Open workspace
                  <ArrowRight className="size-4" aria-hidden />
                </ButtonLink>
              ) : (
                <>
                  <ButtonLink href="/login" variant="outline" className="flex-1">
                    Sign in
                  </ButtonLink>
                  <ButtonLink href="/signup" className="flex-1">
                    Start free
                  </ButtonLink>
                </>
              )}
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
