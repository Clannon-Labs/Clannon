import type { RunStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_META: Record<RunStatus, { label: string; className: string; live?: boolean }> = {
  queued: { label: "Queued", className: "bg-muted text-muted-foreground", live: true },
  sanitizing: { label: "Sanitizing", className: "bg-log-tool/15 text-log-tool", live: true },
  verifying: { label: "Verifying", className: "bg-log-tool/15 text-log-tool", live: true },
  orchestrating: { label: "Researching", className: "bg-primary-soft text-primary", live: true },
  filtering: { label: "Quality filter", className: "bg-memory-soft text-memory", live: true },
  delivered: { label: "Delivered", className: "bg-primary-soft text-primary" },
  blocked: { label: "Blocked", className: "bg-destructive-soft text-destructive" },
  failed: { label: "Failed", className: "bg-destructive-soft text-destructive" },
};

export function RunStatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={cn(
        "tag-label inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
        meta.className,
        className,
      )}
    >
      {meta.live && (
        <span className="size-1.5 animate-pulse-dot rounded-full bg-current" aria-hidden />
      )}
      {meta.label}
    </span>
  );
}

/** Ordered pipeline stages for the run-view stepper. */
export const PIPELINE_STAGES: { key: RunStatus; label: string }[] = [
  { key: "sanitizing", label: "Sanitize" },
  { key: "verifying", label: "Verify" },
  { key: "orchestrating", label: "Orchestrate" },
  { key: "filtering", label: "Filter" },
  { key: "delivered", label: "Deliver" },
];

export function stageIndex(status: RunStatus): number {
  const i = PIPELINE_STAGES.findIndex((s) => s.key === status);
  if (i >= 0) return i;
  if (status === "queued") return -1;
  return PIPELINE_STAGES.length; // terminal failure states
}
