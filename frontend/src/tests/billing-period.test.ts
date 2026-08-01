import { describe, expect, it } from "vitest";
import { fixedBillingPeriod } from "@/lib/billing-period";

describe("fixedBillingPeriod", () => {
  it("clamps a Jan-31 anniversary in February without drifting in March", () => {
    const anchor = new Date("2026-01-31T23:59:00Z");

    expect(fixedBillingPeriod(anchor, new Date("2026-02-28T12:00:00Z"))).toEqual({
      periodStart: "2026-02-28",
      periodEnd: "2026-03-31",
    });
    expect(fixedBillingPeriod(anchor, new Date("2026-03-30T12:00:00Z"))).toEqual({
      periodStart: "2026-02-28",
      periodEnd: "2026-03-31",
    });
    expect(fixedBillingPeriod(anchor, new Date("2026-03-31T00:00:00Z"))).toEqual({
      periodStart: "2026-03-31",
      periodEnd: "2026-04-30",
    });
  });

  it("uses UTC dates, not the browser timezone", () => {
    const anchor = new Date("2026-01-15T23:30:00-08:00"); // Jan 16 UTC
    expect(fixedBillingPeriod(anchor, new Date("2026-02-16T00:01:00Z"))).toEqual({
      periodStart: "2026-02-16",
      periodEnd: "2026-03-16",
    });
  });
});
