import Link from "next/link";
import type { ReactNode } from "react";
import { Mark, Wordmark } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/theme";
import { siteConfig } from "@/config/site.config";
import { LEGAL_PAGES } from "@/components/legal/legal-doc";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      {/* brand panel — pinned to the viewport (h-dvh + sticky) so the ring and
          quote sit at the SAME y on login/signup/forgot, however tall the form
          column runs */}
      <aside className="sticky top-0 hidden h-dvh w-[44%] flex-col justify-between overflow-hidden border-r border-border bg-surface p-10 lg:flex">
        <Link href="/" aria-label={`${siteConfig.name} home`}>
          <Wordmark />
        </Link>

        <div className="relative">
          {/* the panel is a poster — in dark the ring needs twice the ink to
              read at all */}
          <Mark className="size-44 text-primary opacity-[0.13] dark:opacity-30" />
          <blockquote className="mt-8 max-w-sm">
            <p className="display-soft text-[1.8rem] leading-[1.12]">
              “Every run lays down a ring. By the tenth, it knows your clients
              better than your notes do.”
            </p>
          </blockquote>
        </div>

        <p className="text-[13px] text-faint">
          Sourced research · live decision log · memory that compounds
        </p>
      </aside>

      {/* form panel */}
      <main id="main" className="flex flex-1 flex-col px-5 py-8 sm:px-10">
        <div className="flex items-center justify-between">
          <div className="lg:hidden">
            <Link href="/" aria-label={`${siteConfig.name} home`}>
              <Wordmark />
            </Link>
          </div>
          <ThemeToggle className="ml-auto" />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">{children}</div>
        </div>
        <nav
          aria-label="Legal"
          className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 pb-2 pt-6"
        >
          {LEGAL_PAGES.map((page) => (
            <Link
              key={page.href}
              href={page.href}
              className="text-[12px] text-faint underline-offset-2 hover:text-muted-foreground hover:underline"
            >
              {page.title.replace(" Policy", "").replace(" of Service", "")}
            </Link>
          ))}
        </nav>
      </main>
    </div>
  );
}
