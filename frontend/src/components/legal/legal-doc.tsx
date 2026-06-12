import type { ReactNode } from "react";
import Link from "next/link";
import { siteConfig } from "@/config/site.config";

/**
 * Shared frame for the legal documents. Entity name, dates, and
 * contact addresses come from siteConfig.legal / siteConfig.contact —
 * update the config, not the documents.
 */
export function LegalDoc({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: ReactNode;
}) {
  return (
    <article className="mx-auto max-w-3xl px-5 py-14 sm:py-20">
      <p className="tag-label text-primary">Legal</p>
      <h1 className="display mt-4 text-[2.6rem] leading-[1.0] sm:text-[3.2rem]">
        {title}
      </h1>
      <p className="mt-3 text-[13px] text-faint">
        Effective {siteConfig.legal.effectiveDate} · Operated by{" "}
        {siteConfig.legal.entityName}
      </p>
      {intro && (
        <p className="mt-6 text-[15px] leading-relaxed text-muted-foreground">{intro}</p>
      )}
      <div className="report-prose mt-8 max-w-none text-muted-foreground [&_h2]:text-foreground [&_strong]:text-foreground">
        {children}
      </div>
    </article>
  );
}

/** Governing-law sentence that stays neutral until config names one. */
export function governingLawText(): string {
  return siteConfig.legal.governingLaw
    ? siteConfig.legal.governingLaw
    : "the jurisdiction in which the operator is established";
}

export const LEGAL_PAGES = [
  { href: "/legal/terms", title: "Terms of Service", summary: "The agreement that governs your use of the service." },
  { href: "/legal/privacy", title: "Privacy Policy", summary: "What we collect, why, who processes it, and your rights." },
  { href: "/legal/acceptable-use", title: "Acceptable Use Policy", summary: "What you may and may not do with the research pipeline." },
  { href: "/legal/refunds", title: "Refund & Cancellation Policy", summary: "Billing cycles, cancellation, and when refunds apply." },
] as const;

export function LegalIndexLinks() {
  return (
    <ul className="mt-8 grid gap-3 sm:grid-cols-2">
      {LEGAL_PAGES.map((page) => (
        <li key={page.href}>
          <Link
            href={page.href}
            className="block h-full rounded-lg border border-border bg-surface p-5 transition-colors hover:border-border-strong hover:bg-surface-raised"
          >
            <span className="block text-[15px] font-semibold text-foreground">
              {page.title}
            </span>
            <span className="mt-1.5 block text-sm leading-relaxed text-muted-foreground">
              {page.summary}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
