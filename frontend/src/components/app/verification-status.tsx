"use client";

import { ShieldAlert } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { VerifiedSeal } from "@/components/brand/verified-seal";
import { EASE } from "@/components/motion";
import { InfoTip } from "@/components/ui/tooltip";
import type { VerificationState } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Render persisted output-filter truth without turning delivery into a claim. */
export function VerificationStatus({ state }: { state: VerificationState | null }) {
  const reduce = useReducedMotion();

  if (state === "not_applicable") {
    return (
      <span className="tag-label mr-1 text-muted-foreground sm:mr-2">
        No verification needed
      </span>
    );
  }

  if (state === "ungrounded") {
    return (
      <>
        <span className="tag-label mr-1 flex items-center gap-1.5 text-destructive sm:mr-2">
          <ShieldAlert className="size-3.5" aria-hidden />
          <span className="sr-only sm:not-sr-only">Not grounded</span>
        </span>
        <InfoTip
          align="end"
          label="The output filter couldn't ground this report's claims in the research it gathered. Treat it as unverified."
        />
      </>
    );
  }

  if (state !== "grounded" && state !== "partial") return null;

  const grounded = state === "grounded";
  return (
    <>
      <span
        className={cn(
          "tag-label mr-1 flex items-center gap-2 sm:mr-2",
          grounded ? "text-primary" : "text-muted-foreground",
        )}
      >
        <span className="relative inline-flex">
          {!reduce && grounded && (
            <motion.span
              aria-hidden
              className="absolute inset-0 rounded-full bg-primary/25 blur-[3px]"
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: [0.5, 1.6], opacity: [0, 0.7, 0] }}
              transition={{ duration: 0.7, ease: EASE, delay: 0.45, times: [0, 0.4, 1] }}
            />
          )}
          <motion.span
            initial={reduce ? false : { scale: 0.5, opacity: 0, rotate: 10 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            transition={
              reduce
                ? undefined
                : { type: "spring", stiffness: 420, damping: 17, delay: 0.45 }
            }
            className="inline-flex"
          >
            <VerifiedSeal className="size-8" state={state} />
          </motion.span>
        </span>
        <span className="sr-only sm:not-sr-only">
          {grounded ? "Verified" : "Partially verified"}
        </span>
      </span>
      <InfoTip
        align="end"
        label={
          grounded
            ? "Every claim was checked against its source before delivery. If it couldn't be grounded, it wouldn't ship."
            : "Some claims were checked and supported by the research — others couldn't be fully grounded. Read the report with that in mind."
        }
      />
    </>
  );
}
