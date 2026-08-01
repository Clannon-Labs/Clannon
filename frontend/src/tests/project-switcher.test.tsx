import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { Plan } from "@/config/plans";

// Same doubling strategy as memory-page.test.tsx: this is about whether the
// goal/context/reference-files fields are OFFERED at all on a plan without
// wiki, not about query caching, so the hooks are doubled directly.
const createMutate = vi.fn((_input: unknown, opts?: { onSuccess?: (p: { id: string; name: string }) => void }) =>
  opts?.onSuccess?.({ id: "p1", name: "New Co" }),
);
const saveMutate = vi.fn();
const uploadMutate = vi.fn();

const FREE_PLAN: Plan = {
  id: "free",
  name: "Seedling",
  monthlyUsd: 0,
  tokenBudget: 100_000,
  memoryTiers: ["episodic"],
} as Plan;

const STARTER_PLAN: Plan = {
  id: "starter",
  name: "Starter",
  monthlyUsd: 29,
  tokenBudget: 1_000_000,
  memoryTiers: ["episodic", "wiki"],
} as Plan;

let plan: Plan = FREE_PLAN;

vi.mock("@/lib/api/hooks", () => ({
  useMe: () => ({ data: { id: "u1", name: "Test", email: "t@example.com", plan: "free" } }),
  useEffectivePlan: () => plan,
  useProjects: () => ({ data: [], isError: false }),
  useCreateProject: () => ({ mutate: createMutate, isPending: false }),
  useRenameProject: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteProject: () => ({ mutate: vi.fn(), isPending: false }),
  useSaveMemory: () => ({ mutate: saveMutate, isPending: false }),
  useUploadMemory: () => ({ mutate: uploadMutate, isPending: false }),
}));

vi.mock("@/components/app/project-provider", () => ({
  ALL_PROJECTS: "all",
  useCurrentProject: () => undefined,
  useCurrentProjectId: () => undefined,
  useIsAllProjects: () => true,
  useSelectProject: () => vi.fn(),
}));

import { ProjectSwitcher } from "@/components/app/project-switcher";
import { ToastProvider } from "@/components/ui/toast";

function renderSwitcher() {
  return render(
    <ToastProvider>
      <ProjectSwitcher />
    </ToastProvider>,
  );
}

function openNewProjectDialog() {
  fireEvent.click(screen.getByRole("button", { name: /Project/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: "New project" }));
}

beforeEach(() => {
  createMutate.mockClear();
  saveMutate.mockClear();
  uploadMutate.mockClear();
});

describe("ProjectSwitcher — new project, plan-gated wiki fields", () => {
  it("offers goal/context/files when the plan includes wiki", () => {
    plan = STARTER_PLAN;
    renderSwitcher();
    openNewProjectDialog();
    expect(screen.getByLabelText(/What's the goal for this project/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tell Clannon about this client/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add files" })).toBeInTheDocument();
  });

  it("does not render goal/context/files when the plan has no wiki tier", () => {
    plan = FREE_PLAN;
    renderSwitcher();
    openNewProjectDialog();
    expect(screen.queryByLabelText(/What's the goal for this project/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Tell Clannon about this client/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add files" })).not.toBeInTheDocument();
    expect(screen.getByText(/not offered here on your plan/)).toBeInTheDocument();
  });

  it("creates the project with no seedFacts and no follow-up wiki writes on a locked plan", () => {
    plan = FREE_PLAN;
    renderSwitcher();
    openNewProjectDialog();
    // both the New project and Rename dialogs render a "Project name" input
    // (only one is open); the New project one is first in DOM order
    fireEvent.change(screen.getAllByLabelText(/^Project name/)[0], { target: { value: "Acme" } });
    fireEvent.click(screen.getByRole("button", { name: /Create project/ }));
    expect(createMutate).toHaveBeenCalledWith(
      { name: "Acme", seedFacts: undefined },
      expect.anything(),
    );
    expect(saveMutate).not.toHaveBeenCalled();
    expect(uploadMutate).not.toHaveBeenCalled();
  });
});
