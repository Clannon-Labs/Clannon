import type { ReactNode } from "react";
import { Mark } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

/**
 * Conversation primitives used by the no-signup demo and assistant turns.
 * Authenticated sent prompts use TurnPrompt because they own copy/edit actions.
 */

export function UserMessage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex justify-end", className)}>
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md border border-border bg-surface-raised px-4 py-2.5 text-sm leading-relaxed text-foreground">
        {children}
      </div>
    </div>
  );
}

export function AssistantMessage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex gap-3", className)}>
      <span
        className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface"
        aria-hidden
      >
        <Mark className="size-4 text-primary" />
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
