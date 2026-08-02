"use client";

import { Star, X } from "lucide-react";
import type { SavedTemplate } from "@/lib/templates";
import { cn } from "@/lib/utils";

/**
 * One saved template, styled to match the built-in starter-example cards
 * exactly (same card shell) so a saved template reads as "one of my own
 * shortcuts," not a second-class citizen bolted on beside the real ones.
 * The delete affordance follows the same hover/focus-reveal convention as
 * the project switcher's row actions — always visible on touch, revealed on
 * hover/focus on pointer devices.
 */
export function TemplateCard({
  template,
  onUse,
  onDelete,
}: {
  template: SavedTemplate;
  onUse: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group/tpl relative flex items-center gap-3.5 rounded-2xl border border-border bg-surface p-4 text-left transition-colors hover:border-border-strong hover:bg-muted sm:flex-col sm:items-start sm:gap-2.5 sm:rounded-xl",
      )}
    >
      <button type="button" onClick={onUse} className="flex min-w-0 flex-1 items-center gap-3.5 sm:flex-col sm:items-start sm:gap-2.5">
        <Star
          className="size-5 shrink-0 fill-memory text-memory transition-colors"
          aria-hidden
        />
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium leading-snug text-foreground sm:text-[13px]">
            {template.name}
          </span>
          <span className="mt-0.5 line-clamp-1 text-[12px] leading-snug text-muted-foreground sm:mt-0">
            {template.brief}
          </span>
        </span>
      </button>
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Delete template “${template.name}”`}
        className="absolute right-2 top-2 flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-faint opacity-100 transition-colors hover:bg-destructive-soft hover:text-destructive sm:opacity-0 sm:group-hover/tpl:opacity-100 sm:group-focus-within/tpl:opacity-100"
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}
