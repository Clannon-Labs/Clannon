import type { Metadata } from "next";
import { siteConfig } from "@/config/site.config";
import { LegalIndexLinks } from "@/components/legal/legal-doc";

export const metadata: Metadata = { title: "Legal" };

export default function LegalIndexPage() {
  return (
    <div className="mx-auto max-w-3xl px-5 py-14 sm:py-20">
      <p className="tag-label text-primary">Legal</p>
      <h1 className="display mt-3 text-3xl sm:text-4xl">
        The documents that govern {siteConfig.name}
      </h1>
      <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
        Written to be read, not to bury you. If anything here is unclear,
        ask us at{" "}
        <a
          href={`mailto:${siteConfig.contact.legal}`}
          className="text-primary underline underline-offset-2"
        >
          {siteConfig.contact.legal}
        </a>
        .
      </p>
      <LegalIndexLinks />
    </div>
  );
}
