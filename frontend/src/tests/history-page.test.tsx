import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { RunSummary } from "@/lib/api/types";
import type { Project } from "@/lib/api/types";

const runs: RunSummary[] = [
  {
    id: "run_1",
    sessionId: "sess_1",
    title: "UK market entry — DTC skincare brand",
    status: "delivered",
    createdAt: "2026-08-01T10:00:00Z",
    tokensUsed: 312_000,
    expertCount: 3,
  },
  {
    id: "run_2",
    sessionId: "sess_2",
    title: "Competitor teardown — recent US entrants",
    status: "failed",
    createdAt: "2026-08-02T09:00:00Z",
    tokensUsed: 40_000,
    expertCount: 1,
  },
  {
    id: "run_3",
    sessionId: "sess_3",
    title: "Source and profile leads",
    status: "blocked",
    createdAt: "2026-08-02T11:00:00Z",
    tokensUsed: 0,
    expertCount: 0,
  },
];

const project: Project = {
  id: "proj_1",
  name: "Meridian Skincare",
  createdAt: "2026-07-01T00:00:00Z",
  color: "moss",
};

let mockRuns: RunSummary[] | undefined = runs;
let mockLoading = false;

vi.mock("@/lib/api/hooks", () => ({
  useRuns: () => ({ data: mockRuns, isLoading: mockLoading }),
}));

vi.mock("@/components/app/project-provider", () => ({
  useCurrentProject: () => project,
  useCurrentProjectId: () => project.id,
  useIsAllProjects: () => false,
}));

import HistoryPage from "@/app/app/history/page";

describe("HistoryPage", () => {
  it("lists every session, newest first, with status and stats", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    const items = screen.getAllByRole("link");
    expect(items).toHaveLength(3);
    // groupBySession sorts by latest activity — run_3 (11:00) and run_2 (09:00)
    // on 08-02 both outrank run_1 (08-01)
    expect(items[0]).toHaveTextContent("Source and profile leads");
    expect(screen.getByText("UK market entry — DTC skincare brand")).toBeInTheDocument();
    // "Blocked"/"Failed"/"Delivered" each appear twice — once as a filter
    // pill, once as the matching row's status badge
    expect(items[0]).toHaveTextContent("Blocked");
    expect(items[1]).toHaveTextContent("Failed");
    expect(items[2]).toHaveTextContent("Delivered");
  });

  it("filters by search text", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search run history" }), {
      target: { value: "competitor" },
    });

    expect(screen.getByText("Competitor teardown — recent US entrants")).toBeInTheDocument();
    expect(screen.queryByText("UK market entry — DTC skincare brand")).not.toBeInTheDocument();
    expect(screen.queryByText("Source and profile leads")).not.toBeInTheDocument();
  });

  it("filters by status", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("radio", { name: "Blocked" }));

    expect(screen.getByText("Source and profile leads")).toBeInTheDocument();
    expect(screen.queryByText("UK market entry — DTC skincare brand")).not.toBeInTheDocument();
    expect(screen.queryByText("Competitor teardown — recent US entrants")).not.toBeInTheDocument();
  });

  it("combines search and status filters", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("radio", { name: "Failed" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search run history" }), {
      target: { value: "source" }, // matches run_3's title, but not its (blocked) status
    });

    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("shows a genuinely-empty state distinct from a no-matches state", () => {
    mockRuns = [];
    mockLoading = false;
    render(<HistoryPage />);

    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("shows loading skeletons, not an empty state, while runs are still in flight", () => {
    mockRuns = undefined;
    mockLoading = true;
    render(<HistoryPage />);

    expect(screen.queryByText("Nothing here yet")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
