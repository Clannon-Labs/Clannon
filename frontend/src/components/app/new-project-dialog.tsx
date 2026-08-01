"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Paperclip, Plus, X } from "lucide-react";
import {
  useCreateProject,
  useEffectivePlan,
  useMe,
  useSaveMemory,
  useUploadMemory,
} from "@/lib/api/hooks";
import { useCreateProjectDialog, useSelectProject } from "@/components/app/project-provider";
import { ApiError } from "@/lib/api";
import { GOAL_MEMORY_TITLE } from "@/lib/project-goal";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/**
 * The "New project" dialog — name, then three optional fields that all seed
 * the project's wiki (goal + context as entries, files as an import) so
 * Clannon starts with real context instead of a blank project.
 *
 * Mounted exactly ONCE (in AppShell), not per-trigger. Its open state lives
 * in ProjectProvider so both the sidebar's "New project" action and a
 * home-screen CTA can open the same dialog. Sidebar content is duplicated
 * in the DOM for the desktop rail and the mobile drawer (see sidebar.tsx) —
 * if this dialog lived inside ProjectSwitcher instead, that duplication
 * would mean two "New project" dialogs opening at once off one shared flag.
 */
export function NewProjectDialog() {
  const { data: user } = useMe();
  const currentPlan = useEffectivePlan(user?.plan);
  // goal + client context + reference files all become wiki entries — tell
  // the user upfront when their plan can't read wiki back, instead of asking
  // them to type real client details into what looks like a black hole.
  const wikiLocked = !!currentPlan && !currentPlan.memoryTiers.includes("wiki");
  const selectProject = useSelectProject();
  const createProject = useCreateProject();
  const saveGoal = useSaveMemory();
  const uploadRefs = useUploadMemory();
  const toast = useToast();
  const { open, closeDialog } = useCreateProjectDialog();

  const [name, setName] = useState("");
  const [seedFacts, setSeedFacts] = useState("");
  const [goal, setGoal] = useState("");
  const [refFiles, setRefFiles] = useState<File[]>([]);
  const refFileInputRef = useRef<HTMLInputElement>(null);

  // closing always clears the form — guarantees a blank form on the NEXT
  // open regardless of which trigger opened it
  function close() {
    closeDialog();
    setName("");
    setSeedFacts("");
    setGoal("");
    setRefFiles([]);
  }

  function submit(e: React.FormEvent) {
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
          close();
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
              { tier: "wiki", title: GOAL_MEMORY_TITLE, content: trimmedGoal, projectId: project.id },
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

  return (
    <Dialog open={open} onClose={close} title="New project" className="max-w-lg">
      <form className="flex flex-col gap-4" onSubmit={submit}>
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
              <p className="mb-1.5 text-[13px] font-medium text-foreground">Reference files (optional)</p>
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
          <Button type="button" variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" loading={createProject.isPending}>
            <Plus className="size-4" aria-hidden /> Create project
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
