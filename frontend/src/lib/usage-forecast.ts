import type { UsageDay, UsageSummary } from "@/lib/api/types";

/**
 * "Runs like this usually take about 4 minutes" — set expectations before
 * Send, not just narrate progress after. Sourced from the account's own
 * recent p50, never a fabricated global number. `null`/absent means
 * genuinely no data yet (a fresh account), not "instant" — the caller must
 * hide the hint entirely rather than show a fake "0s".
 */
export function formatDurationEstimate(usage: UsageSummary | undefined): string | null {
  const ms = usage?.latency?.totalDurationMs?.p50;
  if (ms === null || ms === undefined) return null;
  const seconds = Math.round(ms / 1000);
  if (seconds < 45) return "under a minute";
  const minutes = Math.round(seconds / 60);
  return minutes === 1 ? "about a minute" : `about ${minutes} minutes`;
}

const MIN_DAYS_OF_SPEND = 2;

/**
 * "~N days left at this pace" — a naive linear projection over the account's
 * own recent daily spend, not a promise. Deliberately conservative: needs at
 * least two days with real spend before projecting anything (one data point
 * is not a rate), and returns `null` once the account is already over
 * budget (that state has its own, more urgent messaging elsewhere) or the
 * recent pace is zero (nothing to divide by, and "infinite days left" is
 * not a useful thing to tell anyone).
 */
export function estimateDaysRemaining(usage: UsageSummary | undefined): number | null {
  if (!usage) return null;
  const remaining = usage.budget - usage.used;
  if (remaining <= 0) return null;

  // today's entry is still accumulating — a partial day understates the
  // real daily rate, so only completed days inform the average
  const completedDays = usage.byDay.slice(0, -1).filter((d: UsageDay) => d.tokens > 0);
  if (completedDays.length < MIN_DAYS_OF_SPEND) return null;

  const avgPerDay = completedDays.reduce((sum, d) => sum + d.tokens, 0) / completedDays.length;
  if (avgPerDay <= 0) return null;

  return Math.max(1, Math.round(remaining / avgPerDay));
}
