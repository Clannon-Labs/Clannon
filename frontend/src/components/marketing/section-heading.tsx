"use client";

import { type ReactNode } from "react";
import { Reveal, Rule } from "@/components/motion";
import { cn } from "@/lib/utils";

/**
 * The editorial masthead every landing section wears: a mono kicker struck
 * through by a drawn rule, then a display headline that rises into place.
 * Headlines use Reveal (fade + rise), not the hero's mask, so multi-line
 * headings never clip a descender.
 */
export function SectionHeading({
  kicker,
  accent = "primary",
  children,
  intro,
  className,
  align = "left",
}: {
  kicker: string;
  accent?: "primary" | "memory";
  children: ReactNode;
  intro?: ReactNode;
  className?: string;
  align?: "left" | "center";
}) {
  const centered = align === "center";
  return (
    <div className={cn(centered && "flex flex-col items-center text-center", className)}>
      <div className={cn("flex items-center gap-4", centered ? "w-full max-w-md" : "")}>
        {centered && <Rule />}
        <p className={cn("tag-label shrink-0", accent === "memory" ? "text-memory" : "text-primary")}>
          {kicker}
        </p>
        <Rule />
      </div>
      <Reveal delay={0.05}>
        <h2
          className={cn(
            "display mt-6 text-balance text-[2.4rem] leading-[0.98] sm:text-[3.2rem]",
            centered ? "max-w-2xl" : "max-w-3xl",
          )}
        >
          {children}
        </h2>
      </Reveal>
      {intro && (
        <Reveal delay={0.12}>
          <p
            className={cn(
              "mt-5 text-[15px] leading-relaxed text-muted-foreground",
              centered ? "max-w-xl" : "max-w-xl",
            )}
          >
            {intro}
          </p>
        </Reveal>
      )}
    </div>
  );
}
