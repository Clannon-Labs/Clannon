import Link from "next/link";
import { Menu, Monitor, Moon, Sun, X } from "lucide-react";
import { Wordmark } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { siteConfig } from "@/config/site.config";
import { MARKETING_NAV as NAV } from "@/config/nav.config";

function ThemeButton() {
  return (
    <button
      type="button"
      data-theme-toggle
      aria-label="Change color theme"
      title="Change theme"
      className="flex size-11 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <Sun className="theme-icon theme-icon-light size-[18px]" aria-hidden />
      <Moon className="theme-icon theme-icon-dark size-[18px]" aria-hidden />
      <Monitor className="theme-icon theme-icon-system size-[18px]" aria-hidden />
    </button>
  );
}

/**
 * Public navigation stays server-rendered. Native details handles mobile
 * disclosure; one tiny delegated theme script in the root layout owns toggles.
 * Landing no longer hydrates a full header merely to watch scroll position.
 */
export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-md">
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
          <ThemeButton />
          <span className="flex items-center gap-3">
            <Link
              href="/login"
              prefetch={false}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Sign in
            </Link>
            <ButtonLink href="/signup" prefetch={false} size="sm">
              Start free
            </ButtonLink>
          </span>
        </div>

        <div className="flex items-center gap-1 md:hidden">
          <ThemeButton />
          <details data-mobile-menu className="group">
            <summary
              aria-label="Open menu"
              className="flex size-11 cursor-pointer list-none items-center justify-center rounded-md text-foreground [&::-webkit-details-marker]:hidden"
            >
              <Menu className="size-5 group-open:hidden" aria-hidden />
              <X className="hidden size-5 group-open:block" aria-hidden />
            </summary>
            <nav
              aria-label="Mobile"
              className="absolute inset-x-0 top-16 border-y border-border bg-background px-5 py-4 shadow-md"
            >
              <div className="mx-auto flex max-w-6xl flex-col gap-1">
                {NAV.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-md px-3 py-3 text-[15px] text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                ))}
                <div className="mt-3 flex items-center gap-3 border-t border-border pt-4">
                  <ButtonLink href="/login" prefetch={false} variant="outline" className="flex-1">
                    Sign in
                  </ButtonLink>
                  <ButtonLink href="/signup" prefetch={false} className="flex-1">
                    Start free
                  </ButtonLink>
                </div>
              </div>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
