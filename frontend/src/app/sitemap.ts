import type { MetadataRoute } from "next";
import { siteConfig } from "@/config/site.config";
import { LEGAL_PAGES } from "@/components/legal/legal-doc";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteConfig.url;
  return [
    { url: base, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/signup`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/login`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${base}/legal`, changeFrequency: "monthly", priority: 0.3 },
    ...LEGAL_PAGES.map((page) => ({
      url: `${base}${page.href}`,
      changeFrequency: "monthly" as const,
      priority: 0.3,
    })),
  ];
}
