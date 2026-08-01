import type { MemoryEntry } from "@/lib/api";

/**
 * The project's goal isn't a schema field — it's a wiki entry written under
 * this exact title by the New Project dialog (see new-project-dialog.tsx).
 * Both the writer and any reader (the pinned goal on the workspace home
 * screen) import this constant so the convention can't drift between them.
 */
export const GOAL_MEMORY_TITLE = "Goal for this project";

export function findGoalEntry(entries: MemoryEntry[] | undefined): MemoryEntry | undefined {
  return entries?.find((e) => e.tier === "wiki" && e.title === GOAL_MEMORY_TITLE);
}
