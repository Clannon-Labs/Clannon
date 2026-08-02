import { describe, it, expect } from "vitest";
import { formatDurationEstimate, estimateDaysRemaining } from "@/lib/usage-forecast";
import type { UsageSummary } from "@/lib/api/types";

function baseUsage(overrides: Partial<UsageSummary> = {}): UsageSummary {
  return {
    periodStart: "2026-08-01",
    periodEnd: "2026-08-31",
    periodEndExclusive: true,
    baseBudget: 1_000_000,
    additionalCredits: 0,
    budget: 1_000_000,
    used: 100_000,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    byDay: [],
    ...overrides,
  };
}

describe("formatDurationEstimate", () => {
  it("returns null when there's no latency data at all", () => {
    expect(formatDurationEstimate(baseUsage())).toBeNull();
  });

  it("returns null (not '0s') when the sample is genuinely empty", () => {
    const usage = baseUsage({
      latency: {
        inPeriod: 0,
        timeToFirstMessageMs: { sampleSize: 0, excluded: 0, p50: null, p95: null },
        totalDurationMs: { sampleSize: 0, excluded: 0, p50: null, p95: null },
      },
    });
    expect(formatDurationEstimate(usage)).toBeNull();
  });

  it("says 'under a minute' below the 45s threshold", () => {
    const usage = baseUsage({
      latency: {
        inPeriod: 1,
        timeToFirstMessageMs: { sampleSize: 1, excluded: 0, p50: 2000, p95: 2000 },
        totalDurationMs: { sampleSize: 1, excluded: 0, p50: 30_000, p95: 30_000 },
      },
    });
    expect(formatDurationEstimate(usage)).toBe("under a minute");
  });

  it("singularizes 'about a minute' for exactly one minute", () => {
    const usage = baseUsage({
      latency: {
        inPeriod: 1,
        timeToFirstMessageMs: { sampleSize: 1, excluded: 0, p50: 2000, p95: 2000 },
        totalDurationMs: { sampleSize: 1, excluded: 0, p50: 58_000, p95: 58_000 },
      },
    });
    expect(formatDurationEstimate(usage)).toBe("about a minute");
  });

  it("pluralizes minutes otherwise", () => {
    const usage = baseUsage({
      latency: {
        inPeriod: 1,
        timeToFirstMessageMs: { sampleSize: 1, excluded: 0, p50: 2000, p95: 2000 },
        totalDurationMs: { sampleSize: 1, excluded: 0, p50: 4 * 60_000, p95: 4 * 60_000 },
      },
    });
    expect(formatDurationEstimate(usage)).toBe("about 4 minutes");
  });
});

describe("estimateDaysRemaining", () => {
  it("returns null with no usage", () => {
    expect(estimateDaysRemaining(undefined)).toBeNull();
  });

  it("returns null when the budget is already spent", () => {
    const usage = baseUsage({
      used: 1_000_000,
      budget: 1_000_000,
      byDay: [
        { date: "2026-08-01", tokens: 500_000 },
        { date: "2026-08-02", tokens: 500_000 },
        { date: "2026-08-03", tokens: 0 },
      ],
    });
    expect(estimateDaysRemaining(usage)).toBeNull();
  });

  it("returns null with fewer than two completed days of real spend", () => {
    const usage = baseUsage({
      used: 100_000,
      budget: 1_000_000,
      byDay: [
        { date: "2026-08-01", tokens: 100_000 },
        { date: "2026-08-02", tokens: 0 }, // today — excluded as partial
      ],
    });
    expect(estimateDaysRemaining(usage)).toBeNull();
  });

  it("projects remaining days from the average of completed days", () => {
    const usage = baseUsage({
      used: 200_000,
      budget: 1_000_000, // 800k remaining
      byDay: [
        { date: "2026-08-01", tokens: 100_000 },
        { date: "2026-08-02", tokens: 100_000 }, // avg 100k/day over 2 completed days
        { date: "2026-08-03", tokens: 0 }, // today — excluded
      ],
    });
    // 800k remaining / 100k per day = 8
    expect(estimateDaysRemaining(usage)).toBe(8);
  });

  it("ignores zero-spend days when averaging, not just when excluding today", () => {
    const usage = baseUsage({
      used: 400_000,
      budget: 1_000_000, // 600k remaining
      byDay: [
        { date: "2026-08-01", tokens: 0 }, // a day with no runs shouldn't drag the average toward zero
        { date: "2026-08-02", tokens: 200_000 },
        { date: "2026-08-03", tokens: 200_000 },
        { date: "2026-08-04", tokens: 0 }, // today
      ],
    });
    // 08-01 excluded (zero), 08-04 excluded (today) — avg over 08-02/08-03 = 200k/day
    // 600k remaining / 200k = 3
    expect(estimateDaysRemaining(usage)).toBe(3);
  });
});
