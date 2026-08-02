import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { UsageSummaryPanel } from "@/components/app/usage-summary";
import TermsPage from "@/app/legal/terms/page";
import type { UsageSummary } from "@/lib/api";

const usage: UsageSummary = {
  periodStart: "2026-07-31",
  periodEnd: "2026-08-31",
  periodEndExclusive: true,
  baseBudget: 2_000_000,
  additionalCredits: 500_000,
  budget: 2_500_000,
  used: 2_100_000,
  cacheReadTokens: 320_000,
  cacheWriteTokens: 40_000,
  byDay: [
    { date: "2026-07-31", tokens: 1_000_000 },
    { date: "2026-08-01", tokens: 1_100_000 },
  ],
};

describe("UsageSummaryPanel", () => {
  it("renders reset boundary, entitlement breakdown, and separate cache diagnostics", () => {
    render(<UsageSummaryPanel usage={usage} />);

    expect(screen.getByText(/Resets Aug 31/)).toBeInTheDocument();
    expect(screen.getByText((_, element) =>
      element?.tagName === "P"
      && element.textContent === "Base 2M + confirmed add-on 500k = 2.5M"
    )).toBeInTheDocument();
    expect(screen.getByText("320k")).toBeInTheDocument();
    expect(screen.getByText("40k")).toBeInTheDocument();
    expect(screen.getByText(/not added to the used-token total/i)).toBeInTheDocument();
  });

  it("states coarse admission honestly and removes atomic hard-stop claims", () => {
    const { container } = render(<UsageSummaryPanel usage={usage} />);
    expect(screen.getByText(/One admitted run can overshoot/)).toBeInTheDocument();
    expect(screen.getByText(/per-call hard stops are not live yet/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/enforced atomically|never mid-charge|stop cleanly at the limit/i);
  });

  it("keeps legal billing copy on the same coarse-admission truth", () => {
    const { container } = render(<TermsPage />);
    expect(screen.getByText(/One already-admitted run may overshoot/)).toBeInTheDocument();
    expect(screen.getByText(/per-call hard stops are not live/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/budget enforcement is atomic|stop cleanly/i);
  });

  it("says nothing about days remaining with fewer than two completed days of spend", () => {
    // the fixture above has one non-today day with real spend — below the
    // forecast's own minimum, so it must stay silent rather than guess
    render(<UsageSummaryPanel usage={usage} />);
    expect(screen.queryByText(/left this period/)).not.toBeInTheDocument();
  });

  it("projects days remaining once there's enough real history", () => {
    const withHistory: UsageSummary = {
      ...usage,
      used: 200_000,
      budget: 1_000_000,
      byDay: [
        { date: "2026-07-30", tokens: 100_000 },
        { date: "2026-07-31", tokens: 100_000 },
        { date: "2026-08-01", tokens: 0 }, // today — excluded as partial
      ],
    };
    render(<UsageSummaryPanel usage={withHistory} />);
    expect(screen.getByText(/left this period/)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });
});
