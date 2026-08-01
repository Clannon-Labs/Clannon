import type { UsageSummary } from "@/lib/api";
import { cn, formatTokens } from "@/lib/utils";

const dayLabel = (date: string) =>
  new Date(`${date}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

export function UsageSummaryPanel({ usage }: { usage: UsageSummary }) {
  const peak = Math.max(...usage.byDay.map((day) => day.tokens), 0);
  const scaleMax = Math.max(peak, 1);
  const pct = usage.budget > 0
    ? Math.min(100, Math.round((usage.used / usage.budget) * 100))
    : 100;

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            Started {dayLabel(usage.periodStart)} · Resets {dayLabel(usage.periodEnd)}
          </p>
          <p className="text-sm tabular">
            <span className="font-semibold text-foreground">{formatTokens(usage.used)}</span>
            <span className="text-faint"> of {formatTokens(usage.budget)} tokens</span>
          </p>
        </div>

        {usage.additionalCredits > 0 && (
          <p className="mt-2 text-[12px] text-muted-foreground tabular">
            Base {formatTokens(usage.baseBudget)} + confirmed add-on {formatTokens(usage.additionalCredits)}
            {" = "}<span className="font-medium text-foreground">{formatTokens(usage.budget)}</span>
          </p>
        )}

        <div
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Token budget used this period"
          className="mt-3 h-2.5 overflow-hidden rounded-full bg-muted"
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-700",
              pct > 90 ? "bg-destructive" : pct > 75 ? "bg-memory" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>

        <p className="mt-3 text-[12px] leading-relaxed text-faint">
          Server checks completed usage before creating each root, follow-up, or revision run.
          One admitted run can overshoot; exact concurrent and per-call hard stops are not live yet.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="flex items-baseline justify-between">
          <h3 className="tag-label text-muted-foreground">Daily spend — current period</h3>
          <p className="font-mono text-[10px] text-faint tabular">peak {formatTokens(peak)}</p>
        </div>
        <div className="relative mt-4 flex h-36 items-end gap-1.5 border-b border-border">
          <span aria-hidden className="pointer-events-none absolute inset-x-0 top-1/2 h-px bg-border/50" />
          {usage.byDay.map((day) => (
            <div
              key={day.date}
              tabIndex={0}
              role="img"
              aria-label={`${dayLabel(day.date)} — ${formatTokens(day.tokens)} tokens`}
              className="group relative flex-1"
            >
              <div
                className={cn(
                  "w-full transition-colors",
                  day.tokens === 0
                    ? "h-[2px] bg-border-strong"
                    : "rounded-t-sm bg-primary/70 group-hover:bg-primary group-focus-within:bg-primary",
                )}
                style={day.tokens === 0 ? undefined : { height: `${Math.max(4, (day.tokens / scaleMax) * 128)}px` }}
              />
              <span className="pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded border border-border bg-surface-raised px-1.5 py-0.5 text-[11px] tabular group-hover:block group-focus-within:block">
                {formatTokens(day.tokens)}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-faint tabular">
          <span>{usage.byDay[0]?.date.slice(5)}</span>
          <span>{usage.byDay.at(-1)?.date.slice(5)}</span>
        </div>
        <p className="sr-only">
          Daily token usage for this period, totalling {formatTokens(usage.used)}.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <h3 className="tag-label text-muted-foreground">Cache traffic · diagnostic</h3>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-[12px] text-faint">Read tokens</dt>
            <dd className="mt-0.5 text-sm font-medium tabular">{formatTokens(usage.cacheReadTokens)}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Write tokens</dt>
            <dd className="mt-0.5 text-sm font-medium tabular">{formatTokens(usage.cacheWriteTokens)}</dd>
          </div>
        </dl>
        <p className="mt-3 text-[12px] leading-relaxed text-faint">
          Cache reads and writes are priced differently by providers. They are cost context only
          and are not added to the used-token total above.
        </p>
      </div>
    </div>
  );
}
