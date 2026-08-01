import Link from "next/link";
import { ApiError, type UsageSummary } from "@/lib/api";
import { formatTokens } from "@/lib/utils";

function resetLabel(periodEnd: string | undefined): string | null {
  if (!periodEnd) return null;
  return new Date(`${periodEnd}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** One actionable rendering for coarse admission refusal, shared by root,
 * follow-up, and revision. Structured 402 actions decide which buttons exist;
 * a proactive GET /usage warning offers only the generic billing route. */
export function BudgetExhaustedNotice({
  error,
  usage,
  forced = false,
}: {
  error?: ApiError | null;
  usage?: UsageSummary;
  forced?: boolean;
}) {
  const structured = error?.status === 402 && error.code === "token_budget_exhausted";
  const exhaustedUsage = usage && usage.used >= usage.budget ? usage : undefined;
  if (!structured && !exhaustedUsage && !forced) return null;

  const used = structured ? error.used : exhaustedUsage?.used;
  const budget = structured ? error.budget : exhaustedUsage?.budget;
  const periodEnd = structured ? error.periodEnd : exhaustedUsage?.periodEnd;
  const reset = resetLabel(periodEnd);
  const actions = structured ? error.actions ?? [] : [];

  return (
    <div
      role={structured ? "alert" : "status"}
      className="mt-2 rounded-lg border border-warning/40 bg-memory-soft px-4 py-3 text-sm"
    >
      <p className="font-medium text-foreground">This billing period is out of tokens.</p>
      <p className="mt-1 leading-relaxed text-muted-foreground">
        {used !== undefined && budget !== undefined
          ? `${formatTokens(used)} used of ${formatTokens(budget)}.`
          : "New runs are paused."}
        {reset ? ` New runs unlock after the reset on ${reset}, or after confirmed billing changes.` : ""}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {actions.map((action) => (
          <Link
            key={action.kind}
            href={`/app/settings?tab=billing&action=${action.kind}`}
            className="inline-flex h-8 items-center rounded-md border border-border-strong bg-surface px-3 text-[12px] font-medium text-foreground transition-colors hover:border-primary hover:text-primary"
          >
            {action.kind === "add_on" ? "Add token credits" : "See upgrade plans"}
          </Link>
        ))}
        {!structured && (
          <Link
            href="/app/settings?tab=billing"
            className="inline-flex h-8 items-center rounded-md border border-border-strong bg-surface px-3 text-[12px] font-medium text-foreground transition-colors hover:border-primary hover:text-primary"
          >
            Review billing options
          </Link>
        )}
      </div>
    </div>
  );
}
