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
  useCreateProject: () => ({ mutate: createMutate, isPending: false }),
  useSaveMemory: () => ({ mutate: saveMutate, isPending: false }),
  useUploadMemory: () => ({ mutate: uploadMutate, isPending: false }),
}));

const closeDialog = vi.fn();

vi.mock("@/components/app/project-provider", () => ({
  useSelectProject: () => vi.fn(),
  // the dialog is mounted once (AppShell) and always open in this test — its
  // own open/close toggling belongs to ProjectProvider, not this component
  useCreateProjectDialog: () => ({ open: true, openDialog: vi.fn(), closeDialog }),
}));

import { NewProjectDialog } from "@/components/app/new-project-dialog";
import { ToastProvider } from "@/components/ui/toast";

function renderDialog() {
  return render(
    <ToastProvider>
      <NewProjectDialog />
    </ToastProvider>,
  );
}

beforeEach(() => {
  closeDialog.mockClear();
  createMutate.mockClear();
  saveMutate.mockClear();
  uploadMutate.mockClear();
});

describe("NewProjectDialog — plan-gated wiki fields", () => {
  it("offers goal/context/files when the plan includes wiki", () => {
    plan = STARTER_PLAN;
    renderDialog();
    expect(screen.getByLabelText(/What's the goal for this project/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tell Clannon about this client/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add files" })).toBeInTheDocument();
  });

  it("does not render goal/context/files when the plan has no wiki tier", () => {
    plan = FREE_PLAN;
    renderDialog();
    expect(screen.queryByLabelText(/What's the goal for this project/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Tell Clannon about this client/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add files" })).not.toBeInTheDocument();
    expect(screen.getByText(/not offered here on your plan/)).toBeInTheDocument();
  });

  it("creates the project with no seedFacts and no follow-up wiki writes on a locked plan", () => {
    plan = FREE_PLAN;
    renderDialog();
    fireEvent.change(screen.getByLabelText(/^Project name/), { target: { value: "Acme" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(createMutate).toHaveBeenCalledWith({ name: "Acme", seedFacts: undefined }, expect.anything());
    expect(saveMutate).not.toHaveBeenCalled();
    expect(uploadMutate).not.toHaveBeenCalled();
  });

  it("sends goal as a separate wiki write on a plan with wiki", () => {
    plan = STARTER_PLAN;
    renderDialog();
    fireEvent.change(screen.getByLabelText(/^Project name/), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText(/What's the goal for this project/), {
      target: { value: "Enter the UK market" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(createMutate).toHaveBeenCalledWith({ name: "Acme", seedFacts: undefined }, expect.anything());
    expect(saveMutate).toHaveBeenCalledWith(
      expect.objectContaining({ tier: "wiki", title: "Goal for this project", content: "Enter the UK market" }),
      expect.anything(),
    );
  });
});
