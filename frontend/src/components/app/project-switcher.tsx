"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronsUpDown, FolderPlus, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import {
  useCreateProject,
  useDeleteProject,
  useProjects,
  useRenameProject,
} from "@/lib/api/hooks";
import { useCurrentProject, useCurrentProjectId, useSelectProject } from "@/components/app/project-provider";
import type { Project } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
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
 * The project (client / body of work) switcher, at the top of the rail. Picking
 * a project scopes the rail's history, the home, and the memory browser to it.
 * Create / rename / delete live here too. Everything is client-side current-project
 * state; each scoped request carries the projectId (see project-provider).
 */
export function ProjectSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const { data: projects, isError } = useProjects();
  const current = useCurrentProject();
  const currentId = useCurrentProjectId();
  const selectProject = useSelectProject();
  const createProject = useCreateProject();
  const renameProject = useRenameProject();
  const deleteProject = useDeleteProject();
  const toast = useToast();

  const [open, setOpen] = useState(false);
  const [rowActions, setRowActions] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);

  // form state for the create / rename dialogs
  const [name, setName] = useState("");
  const [seedFacts, setSeedFacts] = useState("");

  const popRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (popRef.current && !popRef.current.contains(e.target as Node)) {
        setOpen(false);
        setRowActions(null);
      }
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && (setOpen(false), setRowActions(null));
    document.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function pick(id: string) {
    selectProject(id);
    setOpen(false);
    setRowActions(null);
    onNavigate?.();
  }

  function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    createProject.mutate(
      { name, seedFacts: seedFacts.trim() || undefined },
      {
        onSuccess: (project) => {
          selectProject(project.id);
          setCreating(false);
          setName("");
          setSeedFacts("");
          toast({
            title: `Project “${project.name}” created`,
            description: seedFacts.trim() ? "Your notes are in its wiki already." : undefined,
            tone: "success",
          });
        },
      },
    );
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
        if (wasCurrent && fallback) selectProject(fallback.id);
        setDeleting(null);
        toast({ title: "Project deleted", description: "Its conversations and memory are gone.", tone: "success" });
      },
    });
  }

  const rowMenu =
    "flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-[13px] transition-colors";

  // Contract-first: if the backend doesn't serve /projects yet, render nothing
  // rather than a non-working switcher. It appears automatically once projects
  // load — in mock mode now, or against the real backend once it ships them.
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
        <span className={cn("size-2.5 shrink-0 rounded-full", dotClass(current?.color))} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-[10px] uppercase tracking-[0.14em] text-faint">Project</span>
          <span className="block truncate text-[13px] font-medium text-foreground">
            {current?.name ?? "All work"}
          </span>
        </span>
        <ChevronsUpDown className="size-4 shrink-0 text-faint" aria-hidden />
      </button>

      {open && (
        <div
          ref={popRef}
          role="menu"
          className="absolute inset-x-3 top-full z-50 mt-1 overflow-hidden rounded-lg border border-border bg-surface-raised p-1 shadow-xl"
        >
          <p className="px-2.5 py-1.5 text-[10px] uppercase tracking-[0.14em] text-faint">Projects</p>
          <ul className="max-h-[40vh] overflow-y-auto">
            {(projects ?? []).map((p) => (
              <li key={p.id} className="group/row relative">
                <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={p.id === currentId}
                  onClick={() => pick(p.id)}
                  className={cn(rowMenu, "pr-8 hover:bg-muted", p.id === currentId && "bg-muted")}
                >
                  <span className={cn("size-2.5 shrink-0 rounded-full", dotClass(p.color))} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-foreground">{p.name}</span>
                  {p.id === currentId && <Check className="size-3.5 shrink-0 text-primary" aria-hidden />}
                </button>
                <button
                  type="button"
                  onClick={() => setRowActions((id) => (id === p.id ? null : p.id))}
                  aria-label={`Actions for ${p.name}`}
                  className={cn(
                    "absolute right-1 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded text-faint transition-colors hover:bg-border hover:text-foreground",
                    rowActions === p.id ? "opacity-100" : "opacity-0 group-hover/row:opacity-100",
                  )}
                >
                  <MoreHorizontal className="size-3.5" aria-hidden />
                </button>
                {rowActions === p.id && (
                  <div className="absolute right-1 top-full z-10 min-w-[8rem] overflow-hidden rounded-md border border-border bg-surface-raised p-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        setRenaming(p);
                        setName(p.name);
                        setRowActions(null);
                        setOpen(false);
                      }}
                      className={cn(rowMenu, "text-muted-foreground hover:bg-muted hover:text-foreground")}
                    >
                      <Pencil className="size-3.5" aria-hidden /> Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDeleting(p);
                        setRowActions(null);
                        setOpen(false);
                      }}
                      className={cn(rowMenu, "text-destructive hover:bg-destructive-soft")}
                    >
                      <Trash2 className="size-3.5" aria-hidden /> Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          <div className="my-1 h-px bg-border" />
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setName("");
              setSeedFacts("");
              setCreating(true);
            }}
            className={cn(rowMenu, "text-foreground hover:bg-muted")}
          >
            <FolderPlus className="size-4 text-primary" aria-hidden /> New project
          </button>
        </div>
      )}

      {/* new project — name + the optional "tell Clannon about this client" seed */}
      <Dialog open={creating} onClose={() => setCreating(false)} title="New project" className="max-w-lg">
        <form className="flex flex-col gap-4" onSubmit={submitCreate}>
          <Input
            label="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Co. — Q3 retainer"
            autoFocus
            required
            maxLength={80}
          />
          <Textarea
            label="Tell Clannon about this client (optional)"
            value={seedFacts}
            onChange={(e) => setSeedFacts(e.target.value)}
            placeholder="Who they are, voice, constraints, what matters. Saved as the project's first wiki entry — it outranks anything inferred."
            rows={5}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={createProject.isPending}>
              <Plus className="size-4" aria-hidden /> Create project
            </Button>
          </div>
        </form>
      </Dialog>

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
