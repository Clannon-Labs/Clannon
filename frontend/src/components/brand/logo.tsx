/* eslint-disable @next/next/no-img-element --
   brand.config can swap these public assets at runtime. Serving the original
   PNG also avoids recompressing fine logo edges through the image optimizer. */
import { cn } from "@/lib/utils";
import { siteConfig } from "@/config/site.config";
import {
  brandConfig,
  BUILTIN_MARK_RINGS,
  BUILTIN_MARK_CORE_R,
} from "@/config/brand.config";

/**
 * The product mark. Reads `brandConfig.icon`: "builtin" draws the ring SVG
 * (geometry from brand.config), anything else renders that image. Swap the
 * mark product-wide from brand.config.ts — never edit call sites.
 */
export function Mark({ className }: { className?: string }) {
  if (brandConfig.icon !== "builtin") {
    // a generated icon dropped in public/ — currentColor no longer applies,
    // so the asset must carry its own color
    return (
      <img
        src={brandConfig.icon}
        alt=""
        aria-hidden="true"
        width={305}
        height={298}
        className={cn(
          "size-7 object-contain",
          brandConfig.invertOnDark && "[html.dark_&]:invert",
          className,
        )}
      />
    );
  }
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" className={cn("size-7", className)}>
      <circle cx="16" cy="16" r={BUILTIN_MARK_CORE_R} fill="currentColor" />
      {BUILTIN_MARK_RINGS.map((ring) => (
        <circle
          key={ring.r}
          cx="16"
          cy="16"
          r={ring.r}
          stroke="currentColor"
          strokeWidth={ring.width}
          strokeLinecap="round"
          strokeDasharray={ring.dash}
          transform={`rotate(${ring.rotate} 16 16)`}
        />
      ))}
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  // a baked icon+name asset replaces the composed mark when configured
  if (brandConfig.wordmark) {
    return (
      <img
        src={brandConfig.wordmark}
        alt={brandConfig.alt}
        width={1027}
        height={291}
        className={cn(
          "h-7 w-auto object-contain",
          brandConfig.invertOnDark && "[html.dark_&]:invert",
          className,
        )}
      />
    );
  }
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Mark className="text-primary" />
      <span className="font-display text-[1.35rem] font-medium tracking-tight">
        {siteConfig.name}
      </span>
    </span>
  );
}
