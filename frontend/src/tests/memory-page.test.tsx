import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { MemoryEntry } from "@/lib/api/types";
import type { Plan } from "@/config/plans";

// The page composes ~6 react-query hooks + a project-provider context; a full
// QueryClientProvider harness buys nothing here, so the hooks are doubled
// directly — this test is about the delete/undo policy per tier, not caching.
const removeMutate = vi.fn((_id: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
const saveMutate = vi.fn();

const PRO_PLAN: Plan = {
  id: "pro",
  name: "Pro",
  monthlyUsd: 79,
  tokenBudget: 6_000_000,
  memoryTiers: ["episodic", "wiki", "semantic", "procedural"],
} as Plan;

const wikiEntry: MemoryEntry = {
  id: "m1",
  tier: "wiki",
  title: "Wiki fact",
  content: "Hand-written content.",
  updatedAt: new Date().toISOString(),
};

const semanticEntry: MemoryEntry = {
  id: "m3",
  tier: "semantic",
  title: "Inferred fact",
  content: "Pipeline-derived content.",
  updatedAt: new Date().toISOString(),
  savedBy: "memory_curator",
  rationale: "Source-backed and reusable.",
  kind: "fact",
};

vi.mock("@/lib/api/hooks", () => ({
  useMe: () => ({ data: { id: "u1", name: "Test", email: "t@example.com", plan: "pro" } }),
  useMemoryEntries: () => ({ data: [wikiEntry, semanticEntry], isLoading: false }),
  useSaveMemory: () => ({ mutate: saveMutate, isPending: false }),
  useDeleteMemory: () => ({ mutate: removeMutate, isPending: false }),
  useUploadMemory: () => ({ mutate: vi.fn(), isPending: false }),
  useEffectivePlan: () => PRO_PLAN,
}));

vi.mock("@/components/app/project-provider", () => ({
  useCurrentProject: () => undefined,
  useCurrentProjectId: () => undefined,
}));

// framer-motion viewport animation needs IntersectionObserver, absent in jsdom
vi.mock("@/components/brand/memory-rings", () => ({
  MemoryRings: () => null,
}));

import MemoryPage from "@/app/app/memory/page";
import { ToastProvider } from "@/components/ui/toast";

function renderPage() {
  return render(
    <ToastProvider>
      <MemoryPage />
    </ToastProvider>,
  );
}

beforeEach(() => {
  removeMutate.mockClear();
  saveMutate.mockClear();
});

describe("MemoryPage — provenance + tiered delete", () => {
  it("renders curator provenance on an inferred entry", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Semantic/i }));
    expect(await screen.findByText("Inferred fact")).toBeInTheDocument();
    expect(screen.getByText(/memory curator/i)).toBeInTheDocument();
    expect(screen.getByText(/Source-backed and reusable\./)).toBeInTheDocument();
  });

  it("offers delete but not edit on an inferred entry", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Semantic/i }));
    await screen.findByText("Inferred fact");
    expect(screen.getByRole("button", { name: /Delete.*Inferred fact/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit.*Inferred fact/i })).not.toBeInTheDocument();
  });

  it("does not promise undo when deleting an inferred entry", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Semantic/i }));
    await screen.findByText("Inferred fact");
    fireEvent.click(screen.getByRole("button", { name: /Delete.*Inferred fact/i }));
    expect(screen.getByText(/no undo/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(removeMutate).toHaveBeenCalledWith("m3", expect.anything());
    // no recreate call was offered/made for the inferred tier
    expect(saveMutate).not.toHaveBeenCalled();
  });

  it("still offers undo (a real recreate) when deleting a wiki entry", async () => {
    renderPage();
    await screen.findByText("Wiki fact");
    fireEvent.click(screen.getByRole("button", { name: /Delete.*Wiki fact/i }));
    expect(screen.getByText(/few seconds to undo/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(removeMutate).toHaveBeenCalledWith("m1", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ tier: "wiki", title: "Wiki fact" }),
    );
  });
});
