import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
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

const deleteMutateAsync = vi.fn<(sessionId: string) => Promise<void>>(() => Promise.resolve());
const routerPush = vi.fn();
const toastSpy = vi.fn();
let mockPathname = "/app/history";

vi.mock("@/lib/api/hooks", () => ({
  useRuns: () => ({ data: mockRuns, isLoading: mockLoading }),
  useDeleteSession: () => ({ mutateAsync: deleteMutateAsync, isPending: false }),
}));

vi.mock("@/components/app/project-provider", () => ({
  useCurrentProject: () => project,
  useCurrentProjectId: () => project.id,
  useIsAllProjects: () => false,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
  usePathname: () => mockPathname,
}));

vi.mock("@/components/ui/toast", () => ({
  useToast: () => toastSpy,
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

  it("filters sessions to the last 7 or 30 days", () => {
    const now = Date.now();
    mockRuns = [
      {
        ...runs[0],
        id: "run_recent",
        sessionId: "sess_recent",
        title: "Recent market brief",
        createdAt: new Date(now - 2 * 24 * 60 * 60 * 1_000).toISOString(),
      },
      {
        ...runs[1],
        id: "run_this_month",
        sessionId: "sess_this_month",
        title: "Monthly competitor review",
        createdAt: new Date(now - 20 * 24 * 60 * 60 * 1_000).toISOString(),
      },
      {
        ...runs[2],
        id: "run_old",
        sessionId: "sess_old",
        title: "Old sourcing plan",
        createdAt: new Date(now - 45 * 24 * 60 * 60 * 1_000).toISOString(),
      },
    ];
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));
    expect(screen.getByText("Recent market brief")).toBeInTheDocument();
    expect(screen.queryByText("Monthly competitor review")).not.toBeInTheDocument();
    expect(screen.queryByText("Old sourcing plan")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Last 30 days" }));
    expect(screen.getByText("Recent market brief")).toBeInTheDocument();
    expect(screen.getByText("Monthly competitor review")).toBeInTheDocument();
    expect(screen.queryByText("Old sourcing plan")).not.toBeInTheDocument();
  });

  it("names the date filter in the no-matches recovery copy", () => {
    mockRuns = [
      {
        ...runs[0],
        createdAt: new Date(Date.now() - 45 * 24 * 60 * 60 * 1_000).toISOString(),
      },
    ];
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("radio", { name: "Last 7 days" }));

    expect(screen.getByText("No matches")).toBeInTheDocument();
    expect(
      screen.getByText("Try a different search term, status, or date filter."),
    ).toBeInTheDocument();
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

  it("shows a selection toolbar only once a row is checked, and Cancel clears it", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    expect(screen.queryByText(/selected$/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Source and profile leads" }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/selected$/)).not.toBeInTheDocument();
  });

  it("clears selection when a filter changes so hidden rows cannot stay selected", () => {
    mockRuns = runs;
    mockLoading = false;
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Source and profile leads" }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Delivered" }));
    expect(screen.queryByText(/selected$/)).not.toBeInTheDocument();
  });

  it("bulk-deletes every checked session and reports a clean success", async () => {
    mockRuns = runs;
    mockLoading = false;
    mockPathname = "/app/history";
    deleteMutateAsync.mockImplementation(() => Promise.resolve());
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Source and profile leads" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Competitor teardown — recent US entrants" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    expect(screen.getByText("Delete 2 conversations?")).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await vi.waitFor(() => {
      expect(deleteMutateAsync).toHaveBeenCalledWith("sess_3");
      expect(deleteMutateAsync).toHaveBeenCalledWith("sess_2");
    });
    await vi.waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith({ title: "2 conversations deleted", tone: "success" });
    });
    // selection clears after the batch finishes
    expect(screen.queryByText(/selected$/)).not.toBeInTheDocument();
  });

  it("reports an honest partial-failure tally instead of a false clean success", async () => {
    mockRuns = runs;
    mockLoading = false;
    mockPathname = "/app/history";
    deleteMutateAsync.mockImplementation((sessionId: string) =>
      sessionId === "sess_2" ? Promise.reject(new Error("network")) : Promise.resolve(),
    );
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Source and profile leads" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Competitor teardown — recent US entrants" }));
    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await vi.waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith({
        title: "Deleted 1 of 2 — 1 failed",
        tone: "warning",
      });
    });
  });

  it("redirects to the workspace if the currently-open run was among the deleted", async () => {
    mockRuns = runs;
    mockLoading = false;
    mockPathname = "/app/runs/run_3"; // viewing the run that belongs to sess_3
    deleteMutateAsync.mockImplementation(() => Promise.resolve());
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Source and profile leads" }));
    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await vi.waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/app");
    });
  });
});
