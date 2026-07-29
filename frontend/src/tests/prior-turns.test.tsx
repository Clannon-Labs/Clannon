/**
 * Tests for PriorTurns and the MockClient.getRunThread contract.
 *
 * PriorTurns receives `turns: Run[]` and renders every turn oldest-first as a
 * chat thread. The caller (the run page) is responsible for the ordering —
 * which is supplied by getRunThread(), whose own oldest-first contract is
 * pinned in the MockClient contract section below.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, className }: { children?: React.ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useReducedMotion: () => true,
}));

vi.mock("@/components/brand/logo", () => ({
  Mark: ({ className }: { className?: string }) => (
    <span data-testid="clannon-mark" className={className} />
  ),
}));

import { PriorTurns } from "@/components/app/prior-turns";
import { MockClient } from "@/lib/api/mock";
import type { Run } from "@/lib/api/types";

// ---- helpers ----------------------------------------------------------------

function makeTurn(overrides: Partial<Run> & Pick<Run, "id" | "brief" | "createdAt">): Run {
  return {
    title: "Test run",
    status: "delivered",
    tokensUsed: 1000,
    expertCount: 1,
    decisionLog: [],
    experts: [],
    sources: [],
    artifacts: [],
    inputs: [],
    sessionId: "sess_test",
    ...overrides,
  };
}

async function settleMockRun(client: MockClient, id: string) {
  await client.cancelRun(id);
  for await (const event of client.streamRun(id, new AbortController().signal)) {
    expect(event).toEqual({ type: "status", status: "cancelled" });
  }
}

// ---- PriorTurns component tests ---------------------------------------------

describe("PriorTurns", () => {
  it("renders nothing when turns array is empty", () => {
    const { container } = render(<PriorTurns turns={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders each turn's brief as a user message", () => {
    const turns = [
      makeTurn({ id: "r1", brief: "What is the market size?", createdAt: "2026-01-01T09:00:00.000Z" }),
      makeTurn({ id: "r2", brief: "Now compare competitors.", createdAt: "2026-01-01T10:00:00.000Z" }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText("What is the market size?")).toBeInTheDocument();
    expect(screen.getByText("Now compare competitors.")).toBeInTheDocument();
  });

  it("renders turns in the order they are passed (caller supplies oldest-first order)", () => {
    const turns = [
      makeTurn({ id: "r1", brief: "Oldest question", createdAt: "2026-01-01T09:00:00.000Z" }),
      makeTurn({ id: "r2", brief: "Newest question", createdAt: "2026-01-01T10:00:00.000Z" }),
    ];
    render(<PriorTurns turns={turns} />);
    const items = screen.getAllByText(/question$/);
    expect(items[0]).toHaveTextContent("Oldest question");
    expect(items[1]).toHaveTextContent("Newest question");
  });

  it("shows a collapsed report summary for turns with a report", () => {
    const turns = [
      makeTurn({
        id: "r1",
        brief: "Research the UK market",
        createdAt: "2026-01-01T09:00:00.000Z",
        report: "# Analysis\n\nThe UK market is £3.4B.",
      }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText("View the report from this turn")).toBeInTheDocument();
  });

  it("renders the message (conversational note) when present", () => {
    const turns = [
      makeTurn({
        id: "r1",
        brief: "Quick question",
        createdAt: "2026-01-01T09:00:00.000Z",
        message: "I found something interesting about the market.",
      }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText(/I found something interesting/)).toBeInTheDocument();
  });

  it("shows the filter-blocked reason when status=blocked, no report or message", () => {
    const turns = [
      makeTurn({
        id: "r1",
        brief: "Sensitive research task",
        createdAt: "2026-01-01T09:00:00.000Z",
        status: "blocked",
      }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText(/output filter blocked/i)).toBeInTheDocument();
  });

  it("shows the failed reason when status=failed, no report or message", () => {
    const turns = [
      makeTurn({
        id: "r1",
        brief: "A task that failed",
        createdAt: "2026-01-01T09:00:00.000Z",
        status: "failed",
      }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText(/did not complete/i)).toBeInTheDocument();
  });

  it("shows the cancelled reason when status=cancelled, no report or message", () => {
    const turns = [
      makeTurn({
        id: "r1",
        brief: "A task the user stopped",
        createdAt: "2026-01-01T09:00:00.000Z",
        status: "cancelled",
      }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(screen.getByText(/you stopped/i)).toBeInTheDocument();
  });

  it("has an accessible section label for earlier conversation", () => {
    const turns = [
      makeTurn({ id: "r1", brief: "First turn", createdAt: "2026-01-01T09:00:00.000Z" }),
    ];
    render(<PriorTurns turns={turns} />);
    expect(
      screen.getByRole("region", { name: /Earlier in this conversation/i }),
    ).toBeInTheDocument();
  });
});

// ---- MockClient.getRunThread contract tests ---------------------------------
//
// getRunThread returns the retained same-session lineage oldest-first.
// Revisions replace one turn after deleting that turn and its descendants.

describe("MockClient.getRunThread", () => {
  it("returns thread turns in ascending createdAt (oldest-first) order", async () => {
    const client = new MockClient();
    const { id: rootId } = await client.createRun("First brief in the session");
    const { id: followId } = await client.createFollowUp(rootId, "Follow-up question for testing");
    const thread = await client.getRunThread(followId);
    expect(thread.length).toBe(2);
    expect(thread[0].createdAt <= thread[1].createdAt).toBe(true);
  });

  it("includes the root run when called from a follow-up", async () => {
    const client = new MockClient();
    const { id: rootId } = await client.createRun("Root question");
    const { id: followId } = await client.createFollowUp(rootId, "Follow-up question");
    const thread = await client.getRunThread(followId);
    const ids = thread.map((r) => r.id);
    expect(ids).toContain(rootId);
    expect(ids).toContain(followId);
  });

  it("returns a single-element thread for a root run with no follow-ups", async () => {
    const client = new MockClient();
    const { id } = await client.createRun("Standalone question");
    const thread = await client.getRunThread(id);
    expect(thread.length).toBe(1);
    expect(thread[0].id).toBe(id);
  });

  it("all thread members share the same sessionId", async () => {
    const client = new MockClient();
    const { id: rootId } = await client.createRun("Root turn for session check");
    const { id: followId } = await client.createFollowUp(rootId, "Follow-up turn");
    const thread = await client.getRunThread(followId);
    const sessionIds = thread.map((r) => r.sessionId ?? r.id);
    expect(new Set(sessionIds).size).toBe(1);
  });

  it("throws 404 for an unknown run id", async () => {
    const client = new MockClient();
    await expect(client.getRunThread("nonexistent_run_id")).rejects.toMatchObject({ status: 404 });
  });

  it("a middle revision keeps its session, project, and prefix while deleting its suffix", async () => {
    const client = new MockClient();

    const memoryBefore = await client.listMemory();
    const { id: rootId } = await client.createRun(
      "Original root turn",
      [],
      undefined,
      "proj_meridian",
    );
    await settleMockRun(client, rootId);
    const { id: middleId } = await client.createFollowUp(rootId, "Original middle turn");
    await settleMockRun(client, middleId);
    const { id: descendantId } = await client.createFollowUp(middleId, "Later descendant turn");
    await settleMockRun(client, descendantId);
    const originalMiddle = await client.getRun(middleId);

    const { id: revisedId } = await client.reviseRun(middleId, "Corrected middle turn");
    const revisedThread = await client.getRunThread(revisedId);
    const revised = await client.getRun(revisedId);

    expect(revisedThread.map((turn) => turn.brief)).toEqual([
      "Original root turn",
      "Corrected middle turn",
    ]);
    expect(revised.sessionId).toBe(originalMiddle.sessionId);
    expect(revised.projectId).toBe("proj_meridian");
    expect(revised.parentRunId).toBe(rootId);
    await expect(client.getRun(middleId)).rejects.toMatchObject({ status: 404 });
    await expect(client.getRunThread(descendantId)).rejects.toMatchObject({ status: 404 });
    expect(await client.listMemory()).toEqual(memoryBefore);
  }, 10_000);

  it("a root revision removes the entire old conversation and leaves only its replacement", async () => {
    const client = new MockClient();

    const { id: rootId } = await client.createRun(
      "Original root turn",
      [],
      undefined,
      "proj_arch",
    );
    await settleMockRun(client, rootId);
    const originalRoot = await client.getRun(rootId);
    const { id: descendantId } = await client.createFollowUp(rootId, "Discarded follow-up");
    await settleMockRun(client, descendantId);

    const { id: revisedId } = await client.reviseRun(rootId, "Corrected root turn");
    const revised = await client.getRun(revisedId);
    const revisedThread = await client.getRunThread(revisedId);

    expect(revisedThread.map((turn) => turn.brief)).toEqual(["Corrected root turn"]);
    expect(revised.sessionId).toBe(originalRoot.sessionId);
    expect(revised.projectId).toBe("proj_arch");
    expect(revised.parentRunId).toBeNull();
    await expect(client.getRun(rootId)).rejects.toMatchObject({ status: 404 });
    await expect(client.getRun(descendantId)).rejects.toMatchObject({ status: 404 });
  });
});
