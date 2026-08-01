import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// ProjectSwitcher no longer owns the New Project dialog's fields (that's
// new-project-dialog.test.tsx) — it only needs to trigger the SHARED open
// state, since sidebar content is duplicated in the DOM for the desktop rail
// vs. the mobile drawer (see sidebar.tsx) and a per-instance dialog would
// double-open. This is the regression guard for that.
vi.mock("@/lib/api/hooks", () => ({
  useProjects: () => ({ data: [], isError: false }),
  useRenameProject: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteProject: () => ({ mutate: vi.fn(), isPending: false }),
}));

const openDialog = vi.fn();

vi.mock("@/components/app/project-provider", () => ({
  ALL_PROJECTS: "all",
  useCurrentProject: () => undefined,
  useCurrentProjectId: () => undefined,
  useIsAllProjects: () => true,
  useSelectProject: () => vi.fn(),
  useCreateProjectDialog: () => ({ open: false, openDialog, closeDialog: vi.fn() }),
}));

import { ProjectSwitcher } from "@/components/app/project-switcher";
import { ToastProvider } from "@/components/ui/toast";

beforeEach(() => {
  openDialog.mockClear();
});

describe("ProjectSwitcher — New project trigger", () => {
  it("opens the shared dialog state, not a local one", () => {
    render(
      <ToastProvider>
        <ProjectSwitcher />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Project/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "New project" }));
    expect(openDialog).toHaveBeenCalledOnce();
  });
});
