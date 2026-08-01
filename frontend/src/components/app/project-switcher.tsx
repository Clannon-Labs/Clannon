"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronsUpDown, FolderPlus, Layers, Pencil, Trash2 } from "lucide-react";
import { useDeleteProject, useProjects, useRenameProject } from "@/lib/api/hooks";
import {
  ALL_PROJECTS,
  useCreateProjectDialog,
  useCurrentProject,
  useCurrentProjectId,
  useIsAllProjects,
  useSelectProject,
} from "@/components/app/project-provider";
import type { Project } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { menuKeyboardHandler, useFocusTrap } from "@/lib/focus";
import { cn } from "@/lib/utils";

// palette key -> a theme dot color
const DOT: Record<string, string> = {
  moss: "bg-primary",
  clay: "bg-warning",
  indigo: "bg-log-route",
  amber: "bg-memory",
  rose: "bg-destructive",
  slate: "bg-faint",
};
const dotClass = (color?: string) => (color && DOT[color]) || "bg-primary";

/**
 * The project (client / body of work) switcher, at the top of the rail. Picking a
 * project scopes the rail history, the home, and the memory browser to it; "All
 * projects" clears the filter and shows everything. Create / rename / delete live
 * here too. Current-project is client-side state; each scoped request carries the
 * projectId (see project-provider).
 */
export function ProjectSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const { data: projects, isError } = useProjects();
  const current = useCurrentProject();
  const currentId = useCurrentProjectId();
  const isAll = useIsAllProjects();
  const selectProject = useSelectProject();
  const renameProject = useRenameProject();
  const deleteProject = useDeleteProject();
  const toast = useToast();

  // the New Project dialog itself is mounted once, in AppShell — see
  // new-project-dialog.tsx for why (sidebar content is duplicated in the DOM
  // for the desktop rail vs. the mobile drawer; only its open FLAG is shared).
  const { openDialog: openCreating } = useCreateProjectDialog();
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [name, setName] = useState("");

  const popRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // keyboard: focus lands on the first item on open, Tab stays inside (the
  // row actions and "New project" are Tab stops), and closing — Escape, pick,
  // outside click — hands focus back to the trigger. Arrow/Home/End roving
  // across the items is menuKeyboardHandler on the menu itself.
  useFocusTrap(open, popRef);

  function pick(id: string) {
    selectProject(id);
    setOpen(false);
    onNavigate?.();
  }

  function submitRename(e: React.FormEvent) {
    e.preventDefault();
    if (!renaming) return;
    renameProject.mutate(
      { id: renaming.id, name },
      {
        onSuccess: () => {
          setRenaming(null);
          setName("");
          toast({ title: "Project renamed", tone: "success" });
        },
      },
    );
  }

  function confirmDelete() {
    if (!deleting) return;
    const wasCurrent = deleting.id === currentId;
    const fallback = projects?.find((p) => p.id !== deleting.id);
    deleteProject.mutate(deleting.id, {
      onSuccess: () => {
        // drop back to a remaining project, or to All projects if none are left
        if (wasCurrent) selectProject(fallback ? fallback.id : ALL_PROJECTS);
        setDeleting(null);
        toast({ title: "Project deleted", description: "Its conversations and memory are gone.", tone: "success" });
      },
    });
  }

  const item = "flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-[13px] transition-colors";

  // Contract-first: if the backend doesn't serve /projects yet, render nothing
  // rather than a non-working switcher. Appears once projects load (mock now, or
  // the real backend once it ships them).
  if (isError || !projects) return null;

  return (
    <div className="relative px-3 pb-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface-raised px-2.5 py-2 text-left transition-colors hover:border-border-strong"
      >
        {current ? (
          <span className={cn("size-2.5 shrink-0 rounded-full", dotClass(current.color))} aria-hidden />
        ) : (
          <Layers className="size-4 shrink-0 text-faint" aria-hidden />
        )}
        <span className="min-w-0 flex-1">
          <span className="tag-label block text-faint">Project</span>
          <span className="block truncate text-[13px] font-medium text-foreground">
            {current?.name ?? "All projects"}
          </span>
        </span>
        <ChevronsUpDown className="size-4 shrink-0 text-faint" aria-hidden />
      </button>

      {open && (
        <div
          ref={popRef}
          role="menu"
          onKeyDown={(e) => menuKeyboardHandler(popRef.current)(e)}
          className="absolute inset-x-3 top-full z-50 mt-1 flex max-h-[min(60vh,26rem)] flex-col rounded-lg border border-border bg-surface-raised shadow-xl"
        >
          {/* All projects — clears the filter */}
          <div className="p-1">
            <button
              type="button"
              role="menuitemradio"
              aria-checked={isAll}
              onClick={() => pick(ALL_PROJECTS)}
              className={cn(item, "hover:bg-muted", isAll && "bg-muted")}
            >
              <Layers className="size-4 shrink-0 text-faint" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-foreground">All projects</span>
              {isAll && <Check className="size-3.5 shrink-0 text-primary" aria-hidden />}
            </button>
          </div>

          <div className="h-px bg-border" />
          <p className="tag-label px-3 pb-1 pt-2 text-faint">
            Projects {projects.length > 0 && <span className="tabular">· {projects.length}</span>}
          </p>

          {/* the scrollable list — every project + its rename/delete, always reachable */}
          <ul className="min-h-0 flex-1 overflow-y-auto px-1">
            {projects.map((p) => (
              <li key={p.id} className="group/row flex items-center gap-1 rounded transition-colors hover:bg-muted">
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={p.id === currentId}
                  onClick={() => pick(p.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-1.5 text-left text-[13px]"
                >
                  <span className={cn("size-2.5 shrink-0 rounded-full", dotClass(p.color))} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-foreground">{p.name}</span>
                  {p.id === currentId && (
                    <Check className="size-3.5 shrink-0 text-primary group-hover/row:hidden" aria-hidden />
                  )}
                </button>
                {/* inline actions — no nested popup to clip; hover on desktop
                    (or keyboard focus — Tab reaches them), always on touch */}
                <span className="flex shrink-0 items-center gap-0.5 pr-1 opacity-100 md:opacity-0 md:transition-opacity md:group-hover/row:opacity-100 md:group-focus-within/row:opacity-100">
                  <button
                    type="button"
                    onClick={() => {
                      setRenaming(p);
                      setName(p.name);
                      setOpen(false);
                    }}
                    aria-label={`Rename ${p.name}`}
                    className="flex size-7 items-center justify-center rounded text-faint transition-colors hover:bg-border hover:text-foreground"
                  >
                    <Pencil className="size-3.5" aria-hidden />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleting(p);
                      setOpen(false);
                    }}
                    aria-label={`Delete ${p.name}`}
                    className="flex size-7 items-center justify-center rounded text-faint transition-colors hover:bg-destructive-soft hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </button>
                </span>
              </li>
            ))}
          </ul>

          <div className="h-px bg-border" />
          <div className="p-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                openCreating();
              }}
              className={cn(item, "text-foreground hover:bg-muted")}
            >
              <FolderPlus className="size-4 text-primary" aria-hidden /> New project
            </button>
          </div>
        </div>
      )}

      {/* rename */}
      <Dialog open={renaming !== null} onClose={() => setRenaming(null)} title="Rename project">
        <form className="flex flex-col gap-4" onSubmit={submitRename}>
          <Input
            label="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
            maxLength={80}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setRenaming(null)}>
              Cancel
            </Button>
            <Button type="submit" loading={renameProject.isPending}>
              Save
            </Button>
          </div>
        </form>
      </Dialog>

      {/* delete confirm — cascade warning */}
      <Dialog open={deleting !== null} onClose={() => setDeleting(null)} title="Delete this project?">
        {deleting && (
          <div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              “{deleting.name}” and <strong>all its conversations and memory</strong> will be
              permanently removed. This can&apos;t be undone.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setDeleting(null)}>
                Keep it
              </Button>
              <Button variant="destructive" loading={deleteProject.isPending} onClick={confirmDelete}>
                Delete project
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
