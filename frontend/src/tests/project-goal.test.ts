import { describe, it, expect } from "vitest";
import { findGoalEntry, GOAL_MEMORY_TITLE } from "@/lib/project-goal";
import type { MemoryEntry } from "@/lib/api/types";

function entry(overrides: Partial<MemoryEntry>): MemoryEntry {
  return {
    id: "m1",
    tier: "wiki",
    title: "Untitled",
    content: "",
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

describe("findGoalEntry", () => {
  it("finds the wiki entry written under the goal title", () => {
    const entries = [
      entry({ id: "m1", title: "Client: Acme — context", content: "voice, budget" }),
      entry({ id: "m2", title: GOAL_MEMORY_TITLE, content: "Enter the UK market" }),
    ];
    expect(findGoalEntry(entries)?.id).toBe("m2");
  });

  it("ignores a same-titled entry outside the wiki tier", () => {
    const entries = [entry({ tier: "episodic", title: GOAL_MEMORY_TITLE, content: "not a goal" })];
    expect(findGoalEntry(entries)).toBeUndefined();
  });

  it("returns undefined when no project has a goal yet", () => {
    expect(findGoalEntry([entry({ title: "Something else" })])).toBeUndefined();
    expect(findGoalEntry(undefined)).toBeUndefined();
    expect(findGoalEntry([])).toBeUndefined();
  });
});
