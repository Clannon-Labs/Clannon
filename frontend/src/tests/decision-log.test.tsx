/**
 * Tests for DecisionLog — pins the live decision-log contract and verifies it
 * stays structurally distinct from the final report (report.tsx renders prose;
 * the log renders kind-labelled ledger entries, never markdown).
 *
 * These are characterization tests: they describe reality as observed. If a
 * test fails after a change to the component, it means the component's observed
 * behaviour diverged from the contract pinned here.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("motion/react", () => ({
  motion: {
    li: ({ children, className }: { children?: React.ReactNode; className?: string }) => (
      <li className={className}>{children}</li>
    ),
  },
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useReducedMotion: () => true,
}));

// @/components/motion exports EASE (a constant) and motion-based layout
// components. With motion/react mocked above, the module loads cleanly.

import { DecisionLog } from "@/components/app/decision-log";
import type { DecisionLogEntry } from "@/lib/api/types";

// ---- helpers ----------------------------------------------------------------

function makeEntry(overrides: Partial<DecisionLogEntry> = {}): DecisionLogEntry {
  return {
    id: "log_default",
    ts: "2026-01-01T12:00:00.000Z",
    kind: "route",
    title: "Routing to market research expert",
    ...overrides,
  };
}

// ---- DecisionLog component tests -------------------------------------------

describe("DecisionLog", () => {
  // Pass 3: an empty LIVE ledger reserves its geometry with ghost rules
  // (no caption — the status band is the only voice); an empty settled
  // ledger states the fact plainly.
  it("shows the empty-history line when a settled run has no entries", () => {
    render(<DecisionLog entries={[]} live={false} />);
    expect(screen.getByText(/No decisions were logged/i)).toBeInTheDocument();
  });

  it("reserves ghost rows (no caption) when live with no entries yet", () => {
    const { container } = render(<DecisionLog entries={[]} live={true} />);
    expect(screen.queryByText(/No decisions were logged/i)).not.toBeInTheDocument();
    expect(container.querySelectorAll("ol[aria-hidden] li").length).toBeGreaterThan(0);
  });

  it("renders each entry's title", () => {
    const entries: DecisionLogEntry[] = [
      makeEntry({ id: "log_1", kind: "route", title: "First decision" }),
      makeEntry({ id: "log_2", kind: "expert_spawn", title: "Second decision" }),
    ];
    render(<DecisionLog entries={entries} live={false} />);
    expect(screen.getByText("First decision")).toBeInTheDocument();
    expect(screen.getByText("Second decision")).toBeInTheDocument();
  });

  it("renders the correct kind label for a route entry", () => {
    render(<DecisionLog entries={[makeEntry({ kind: "route", title: "Decided route" })]} live={false} />);
    expect(screen.getByText("ROUTE")).toBeInTheDocument();
  });

  it("renders the correct kind label for an expert_spawn entry", () => {
    render(<DecisionLog entries={[makeEntry({ kind: "expert_spawn", title: "Spawning expert" })]} live={false} />);
    expect(screen.getByText("EXPERT")).toBeInTheDocument();
  });

  it("renders ANSWER label for answer-kind entries (the final payoff line)", () => {
    render(<DecisionLog entries={[makeEntry({ kind: "answer", title: "Research complete" })]} live={false} />);
    expect(screen.getByText("ANSWER")).toBeInTheDocument();
  });

  it("renders WARN label for warning-kind entries", () => {
    render(<DecisionLog entries={[makeEntry({ kind: "warning", title: "Rate limit approaching" })]} live={false} />);
    expect(screen.getByText("WARN")).toBeInTheDocument();
  });

  // Pass 2: the LIVE/DONE badge left the masthead — RunActivity's status band
  // is the one status voice. The ledger header carries only the entry count.
  it("shows the entry count in the header", () => {
    const entries = [
      makeEntry({ id: "log_1", kind: "route" }),
      makeEntry({ id: "log_2", kind: "expert_spawn" }),
    ];
    render(<DecisionLog entries={entries} live={false} />);
    expect(screen.getByText(/2 entries/)).toBeInTheDocument();
  });

  it("does not render its own LIVE/DONE badge (the status band owns status)", () => {
    render(<DecisionLog entries={[makeEntry()]} live={true} />);
    expect(screen.queryByText(/LIVE/)).toBeNull();
    expect(screen.queryByText(/DONE/)).toBeNull();
  });

  it("shows entry detail text when present", () => {
    render(
      <DecisionLog
        entries={[makeEntry({ kind: "route", title: "Routing", detail: "entropy=0.82" })]}
        live={false}
      />,
    );
    expect(screen.getByText("entropy=0.82")).toBeInTheDocument();
  });

  it("renders meta key=value pairs when present", () => {
    render(
      <DecisionLog
        entries={[
          makeEntry({
            kind: "tool_call",
            title: "Web search",
            meta: { tool: "web_search", query: "UK skincare market" },
          }),
        ]}
        live={false}
      />,
    );
    expect(screen.getByText("web_search")).toBeInTheDocument();
  });

  it("renders a recall entry (tool_call with tool=recall) in memory amber style", () => {
    render(
      <DecisionLog
        entries={[
          makeEntry({
            id: "log_recall",
            kind: "tool_call",
            title: "Recall earlier context",
            meta: { tool: "recall", query: "What did we decide about pricing?" },
          }),
        ]}
        live={false}
      />,
    );
    // A recall entry is displayed as "Looking back at our earlier conversation"
    expect(screen.getByText("Looking back at our earlier conversation")).toBeInTheDocument();
    // The query is displayed in italics (with surrounding quotes as siblings — match the body text)
    expect(screen.getByText(/What did we decide about pricing/i)).toBeInTheDocument();
  });

  // --- Distinctness from report.tsx ----------------------------------------
  //
  // The decision log and the final report are two separate rendering surfaces.
  // The log renders structured kind labels (ROUTE, EXPERT, ...) via ledger
  // entries. The report renders markdown prose via report-prose class. Confirm
  // the log surface never produces the report's markdown container.

  it("contains no report-prose container — stays distinct from the report surface", () => {
    const entries = [
      makeEntry({ id: "log_1", kind: "route", title: "Routing decision" }),
      makeEntry({ id: "log_2", kind: "answer", title: "Final answer ready" }),
    ];
    render(<DecisionLog entries={entries} live={false} />);
    expect(document.querySelector(".report-prose")).toBeNull();
  });

  it("has an accessible section label for the orchestrator decision log", () => {
    render(<DecisionLog entries={[]} live={false} />);
    expect(screen.getByRole("region", { name: /Orchestrator decision log/i })).toBeInTheDocument();
  });
});
