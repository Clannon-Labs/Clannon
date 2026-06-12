import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";
import { siteConfig } from "@/config/site.config";
import { MARKETING_NAV } from "@/config/nav.config";
import { LEGAL_PAGES } from "@/components/legal/legal-doc";

export function MarketingFooter() {
  return (
    <footer className="hairline-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-5 py-12 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-xs">
          <Wordmark />
          {siteConfig.footer.engineLine && (
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              {siteConfig.footer.engineLine}
            </p>
          )}
        </div>

        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-12 gap-y-2 text-sm sm:grid-cols-3 sm:gap-x-16">
          <div className="flex flex-col gap-1">
            <span className="tag-label mb-1.5 text-faint">Product</span>
            {MARKETING_NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="py-1 text-muted-foreground hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="flex flex-col gap-1">
            <span className="tag-label mb-1.5 text-faint">Account</span>
            <Link href="/login" className="py-1 text-muted-foreground hover:text-foreground">Sign in</Link>
            <Link href="/signup" className="py-1 text-muted-foreground hover:text-foreground">Start free</Link>
          </div>
          <div className="flex flex-col gap-1">
            <span className="tag-label mb-1.5 text-faint">Legal</span>
            {LEGAL_PAGES.map((page) => (
              <Link
                key={page.href}
                href={page.href}
                className="py-1 text-muted-foreground hover:text-foreground"
              >
                {page.title.replace(" Policy", "").replace(" of Service", "")}
              </Link>
            ))}
          </div>
        </nav>
      </div>
      <div className="hairline-t">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
          <p className="text-[13px] text-faint">
            © {new Date().getFullYear()} {siteConfig.legal.entityName}
          </p>
          {siteConfig.footer.credit && (
            <p className="tag-label text-faint">{siteConfig.footer.credit}</p>
          )}
        </div>
      </div>
    </footer>
  );
}
