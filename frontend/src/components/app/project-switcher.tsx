"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronsUpDown, FolderPlus, Layers, Paperclip, Pencil, Plus, Trash2, X } from "lucide-react";
import {
  useCreateProject,
  useDeleteProject,
  useEffectivePlan,
  useMe,
  useProjects,
  useRenameProject,
  useSaveMemory,
  useUploadMemory,
} from "@/lib/api/hooks";
import {
  ALL_PROJECTS,
  useCurrentProject,
  useCurrentProjectId,
  useIsAllProjects,
  useSelectProject,
} from "@/components/app/project-provider";
import { ApiError, type Project } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
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
  const { data: user } = useMe();
  const currentPlan = useEffectivePlan(user?.plan);
  // goal + client context + reference files all become wiki entries — tell
  // the user upfront when their plan can't read wiki back, instead of asking
  // them to type real client details into what looks like a black hole.
  const wikiLocked = !!currentPlan && !currentPlan.memoryTiers.includes("wiki");
  const { data: projects, isError } = useProjects();
  const current = useCurrentProject();
  const currentId = useCurrentProjectId();
  const isAll = useIsAllProjects();
  const selectProject = useSelectProject();
  const createProject = useCreateProject();
  const renameProject = useRenameProject();
  const deleteProject = useDeleteProject();
  const saveGoal = useSaveMemory();
  const uploadRefs = useUploadMemory();
  const toast = useToast();

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);

  // form state for the create / rename dialogs
  const [name, setName] = useState("");
  const [seedFacts, setSeedFacts] = useState("");
  // goal + reference files are optional and only apply to creation, not rename
  const [goal, setGoal] = useState("");
  const [refFiles, setRefFiles] = useState<File[]>([]);
  const refFileInputRef = useRef<HTMLInputElement>(null);

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

  function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    // wikiLocked also guards here, not just the render: nothing typed while
    // unlocked-then-downgraded-mid-session should slip through either.
    const trimmedSeed = wikiLocked ? "" : seedFacts.trim();
    const trimmedGoal = wikiLocked ? "" : goal.trim();
    const pendingFiles = wikiLocked ? [] : refFiles;
    createProject.mutate(
      { name, seedFacts: trimmedSeed || undefined },
      {
        onSuccess: (project) => {
          selectProject(project.id);
          setCreating(false);
          setName("");
          setSeedFacts("");
          setGoal("");
          setRefFiles([]);
          toast({
            title: `Project “${project.name}” created`,
            description: trimmedSeed ? "Your notes are in its wiki already." : undefined,
            tone: "success",
          });
          // goal + files are separate wiki writes, best-effort: the project
          // itself is already real by this point, so a failure here is a
          // toast pointing at the Memory tab, never a rollback.
          if (trimmedGoal) {
            saveGoal.mutate(
              { tier: "wiki", title: "Goal for this project", content: trimmedGoal, projectId: project.id },
              {
                onError: (err) =>
                  toast({
                    title: "Goal wasn’t saved",
                    description:
                      err instanceof ApiError ? err.message : "Add it from the project’s Memory tab instead.",
                    tone: "warning",
                  }),
              },
            );
          }
          if (pendingFiles.length > 0) {
            uploadRefs.mutate(
              { files: pendingFiles, projectId: project.id },
              {
                onError: (err) =>
                  toast({
                    title: "Reference files weren’t imported",
                    description:
                      err instanceof ApiError ? err.message : "Try uploading again from the Memory tab.",
                    tone: "warning",
                  }),
              },
            );
          }
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
                setName("");
                setSeedFacts("");
                setGoal("");
                setRefFiles([]);
                setCreating(true);
              }}
              className={cn(item, "text-foreground hover:bg-muted")}
            >
              <FolderPlus className="size-4 text-primary" aria-hidden /> New project
            </button>
          </div>
        </div>
      )}

      {/* new project — name, then three optional fields that all seed the
          project's wiki (goal + context as entries, files as an import) so
          Clannon starts with real context instead of a blank project */}
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
          {wikiLocked ? (
            // Locked plan: don't render inputs that lead nowhere but a wiki
            // this account can't read back. Nothing typed here can reach
            // wiki if the fields never exist — no separate "don't submit
            // it" logic needed downstream.
            <p className="-mt-1 rounded-md bg-muted px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">
              Goal, client context, and reference files save to this
              project&apos;s wiki, which unlocks on Starter — they&apos;re not
              offered here on your plan.{" "}
              <Link href="/app/settings?tab=billing" className="text-primary hover:underline">
                See plans
              </Link>
              .
            </p>
          ) : (
            <>
              <Textarea
                label="What's the goal for this project? (optional)"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Enter the UK market this year without eroding the ceramide serum's margin."
                rows={3}
              />
              <Textarea
                label="Tell Clannon about this client (optional)"
                value={seedFacts}
                onChange={(e) => setSeedFacts(e.target.value)}
                placeholder="Who they are, voice, constraints, what matters. Saved as the project's first wiki entry — it outranks anything inferred."
                rows={4}
              />
              <div>
                <p className="mb-1.5 text-[13px] font-medium text-foreground">
                  Reference files (optional)
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => refFileInputRef.current?.click()}
                >
                  <Paperclip className="size-4" aria-hidden /> Add files
                </Button>
                <input
                  ref={refFileInputRef}
                  type="file"
                  multiple
                  accept=".md,.markdown,.txt"
                  className="hidden"
                  aria-label="Attach reference files to this project"
                  onChange={(e) => {
                    const picked = Array.from(e.target.files ?? []);
                    e.target.value = ""; // allow re-picking the same file
                    if (picked.length) setRefFiles((prev) => [...prev, ...picked]);
                  }}
                />
                {refFiles.length > 0 && (
                  <ul className="mt-2 flex flex-col gap-1">
                    {refFiles.map((file, i) => (
                      <li
                        key={`${file.name}-${i}`}
                        className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] text-muted-foreground"
                      >
                        <span className="min-w-0 truncate">{file.name}</span>
                        <button
                          type="button"
                          onClick={() => setRefFiles((prev) => prev.filter((_, j) => j !== i))}
                          aria-label={`Remove ${file.name}`}
                          className="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded text-faint hover:bg-muted hover:text-foreground"
                        >
                          <X className="size-3.5" aria-hidden />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-1.5 text-[12px] text-faint">
                  Markdown or text — imported straight into the project&apos;s wiki.
                </p>
              </div>
            </>
          )}
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
