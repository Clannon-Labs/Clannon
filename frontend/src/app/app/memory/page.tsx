"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { BookMarked, ChevronDown, ChevronUp, Lock, Pencil, Plus, Search, Trash2, Upload } from "lucide-react";
import {
  useDeleteMemory,
  useEffectivePlan,
  useUploadMemory,
  useMe,
  useMemoryEntries,
  useSaveMemory,
} from "@/lib/api/hooks";
import { useCurrentProject, useCurrentProjectId } from "@/components/app/project-provider";
import type { MemoryEntry } from "@/lib/api";
import { TIER_LABELS, type MemoryTier } from "@/config/plans";
import { ApiError } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { Report } from "@/components/app/report";
import { formatRelativeTime } from "@/lib/utils";

const TIER_ORDER: MemoryTier[] = ["wiki", "semantic", "episodic", "procedural"];

const TIER_COPY: Record<MemoryTier, { hint: string; locked: string }> = {
  wiki: {
    hint: "Your editable source of truth. On any conflict, wiki wins — over everything the system has inferred.",
    locked: "Wiki memory unlocks on Starter. Write client facts once; every future run starts already knowing them.",
  },
  semantic: {
    hint: "Facts Clannon has learned, each with provenance and confidence. Read-only — corrections belong in your wiki, which outranks these.",
    locked: "Semantic memory unlocks on Pro. A growing graph of source-backed facts about your clients and domains.",
  },
  episodic: {
    hint: "What happened: runs, outcomes, decisions. This is the baseline tier — included on every plan.",
    locked: "",
  },
  procedural: {
    hint: "How you like to work — formats, conventions, recurring moves. Learned over time, applied automatically.",
    locked: "Procedural memory unlocks on Pro. The tenth report follows your conventions without being told.",
  },
};

/* Collapse threshold for entry content — roughly 8 lines of rendered prose.
   Imported files can be whole documents; the card shows a preview and the
   reader opens the rest in place. */
const ENTRY_PREVIEW_PX = 176;

function EntryCard({
  entry,
  editable,
  onEdit,
  onDelete,
}: {
  entry: MemoryEntry;
  editable: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  // measure the rendered markdown, not the raw text — a long file clamps,
  // a short one never shows the toggle
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const measure = () => setOverflows(el.scrollHeight > ENTRY_PREVIEW_PX + 24);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [entry.content]);

  return (
    <article className="rounded-lg border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold leading-snug">{entry.title}</h3>
        {editable && (
          <div className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={onEdit}
              aria-label={`Edit “${entry.title}”`}
              className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-muted hover:text-foreground"
            >
              <Pencil className="size-4" />
            </button>
            <button
              type="button"
              onClick={onDelete}
              aria-label={`Delete “${entry.title}”`}
              className="flex size-10 cursor-pointer items-center justify-center rounded-md text-faint transition-colors hover:bg-destructive-soft hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        )}
      </div>
      {/* wiki entries are markdown — render them, don't show bare #/* */}
      <div className="relative mt-2 text-muted-foreground">
        <div
          ref={contentRef}
          style={!expanded && overflows ? { maxHeight: ENTRY_PREVIEW_PX } : undefined}
          className={!expanded && overflows ? "overflow-hidden" : undefined}
        >
          <Report markdown={entry.content} className="text-sm" />
        </div>
        {!expanded && overflows && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface to-transparent"
          />
        )}
      </div>
      {overflows && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((e) => !e)}
          className="mt-1 flex min-h-9 cursor-pointer items-center gap-1 text-[13px] font-medium text-primary hover:underline underline-offset-4"
        >
          {expanded ? (
            <>Collapse <ChevronUp className="size-3.5" aria-hidden /></>
          ) : (
            <>Read the whole entry <ChevronDown className="size-3.5" aria-hidden /></>
          )}
        </button>
      )}
      <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-faint">
        <span>{formatRelativeTime(entry.updatedAt)}</span>
        {entry.confidence !== undefined && (
          <span className="tabular">confidence {Math.round(entry.confidence * 100)}%</span>
        )}
        {entry.source && <span>from {entry.source}</span>}
        {entry.runId && <span className="font-mono">{entry.runId}</span>}
      </p>
    </article>
  );
}

export default function MemoryPage() {
  const { data: user } = useMe();
  const projectId = useCurrentProjectId();
  const currentProject = useCurrentProject();
  const { data: entries, isLoading } = useMemoryEntries(projectId);
  const save = useSaveMemory();
  const remove = useDeleteMemory();
  const upload = useUploadMemory();
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [editing, setEditing] = useState<Partial<MemoryEntry> | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<MemoryEntry | null>(null);
  const [query, setQuery] = useState("");

  const currentPlan = useEffectivePlan(user?.plan);
  const unlockedTiers = currentPlan?.memoryTiers ?? [];

  const byTier = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const map = new Map<MemoryTier, MemoryEntry[]>();
    for (const tier of TIER_ORDER) map.set(tier, []);
    for (const entry of entries ?? []) {
      if (
        needle &&
        !entry.title.toLowerCase().includes(needle) &&
        !entry.content.toLowerCase().includes(needle)
      ) {
        continue;
      }
      map.get(entry.tier)?.push(entry);
    }
    return map;
  }, [entries, query]);

  function deleteWithUndo(entry: MemoryEntry) {
    remove.mutate(entry.id, {
      onSuccess: () => {
        setConfirmDelete(null);
        toast({
          title: "Wiki entry deleted",
          description: `“${entry.title}” is no longer visible to agents.`,
          action: {
            label: "Undo",
            onClick: () =>
              save.mutate({
                tier: entry.tier,
                title: entry.title,
                content: entry.content,
                projectId: entry.projectId,
              }),
          },
        });
      },
    });
  }

  return (
    <div className="mx-auto max-w-4xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="tag-label text-memory">
            Memory{currentProject ? ` · ${currentProject.name}` : ""}
          </p>
          <h1 className="display mt-3 text-[2.4rem] leading-[1.0]">
            The archive
          </h1>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
            {currentProject
              ? `Everything Clannon knows for ${currentProject.name}, by tier. Wiki entries are yours to write — and they outrank everything else.`
              : "Everything Clannon knows on your behalf, by tier. Wiki entries are yours to write — and they outrank everything else."}
          </p>
        </div>
      </header>

      <div className="relative mt-7 max-w-sm">
        <Search
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint"
          aria-hidden
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the archive…"
          aria-label="Search memory entries"
          className="h-10 w-full rounded-md border border-border-strong bg-surface-raised pl-10 pr-3.5 text-base text-foreground placeholder:text-faint focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 sm:text-sm"
        />
      </div>

      <Tabs defaultValue="wiki" className="mt-5">
        {/* the tier row scrolls on a phone — no scrollbar, a right-edge fade
            says "more" instead of a hard clip */}
        <div className="relative max-w-full">
          <TabsList className="scrollbar-none max-w-full overflow-x-auto">
            {TIER_ORDER.map((tier) => (
              <TabsTrigger key={tier} value={tier} className="shrink-0">
                <span className="flex items-center gap-1.5">
                  {!unlockedTiers.includes(tier) && <Lock className="size-3" aria-hidden />}
                  {TIER_LABELS[tier]}
                  <span className="text-faint tabular">{byTier.get(tier)?.length ?? 0}</span>
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 w-14 rounded-r-md bg-gradient-to-l from-muted via-muted/70 to-transparent sm:hidden"
          />
        </div>

        {TIER_ORDER.map((tier) => {
          const unlocked = unlockedTiers.includes(tier);
          const tierEntries = byTier.get(tier) ?? [];
          const isWiki = tier === "wiki";

          return (
            <TabsContent key={tier} value={tier} className="mt-6">
              {!unlocked ? (
                <EmptyState
                  icon={<Lock className="size-7" aria-hidden />}
                  title={`${TIER_LABELS[tier]} memory is locked on your plan`}
                  description={TIER_COPY[tier].locked}
                  action={
                    <ButtonLink href="/app/settings?tab=billing">See plans</ButtonLink>
                  }
                />
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="max-w-xl text-[13px] leading-relaxed text-muted-foreground">
                      {TIER_COPY[tier].hint}
                    </p>
                    {isWiki && (
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          loading={upload.isPending}
                          onClick={() => fileInputRef.current?.click()}
                        >
                          <Upload className="size-4" aria-hidden />
                          {upload.isPending ? "Importing…" : "Upload files"}
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => setEditing({ tier: "wiki", title: "", content: "" })}
                        >
                          <Plus className="size-4" aria-hidden /> New entry
                        </Button>
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".md,.markdown,.txt"
                          multiple
                          className="hidden"
                          aria-label="Upload markdown files to your wiki"
                          onChange={(e) => {
                            const files = Array.from(e.target.files ?? []);
                            e.target.value = ""; // allow re-selecting the same file
                            if (files.length === 0) return;
                            upload.mutate(
                              { files, projectId },
                              {
                              onSuccess: (entries) =>
                                toast({
                                  title: `${entries.length} ${entries.length === 1 ? "file" : "files"} imported to your wiki`,
                                  description: "Agents see them on the very next run.",
                                  tone: "success",
                                }),
                              onError: (err) =>
                                toast({
                                  title: "Upload failed",
                                  description:
                                    err instanceof ApiError ? err.message : "Nothing was imported — try again.",
                                  tone: "warning",
                                }),
                            });
                          }}
                        />
                      </div>
                    )}
                  </div>

                  {isLoading ? (
                    <div className="mt-5 flex flex-col gap-3">
                      <Skeleton className="h-32" />
                      <Skeleton className="h-32" />
                    </div>
                  ) : tierEntries.length === 0 ? (
                    <EmptyState
                      className="mt-5"
                      icon={<BookMarked className="size-7" aria-hidden />}
                      title={isWiki ? "Your wiki is empty" : "Nothing here yet"}
                      description={
                        isWiki
                          ? "Add client facts, style guides, or preferences. Agents read these before every run."
                          : "This tier fills as you run research. It's written by the pipeline's memory policies, not by hand."
                      }
                      action={
                        isWiki ? (
                          <Button onClick={() => setEditing({ tier: "wiki", title: "", content: "" })}>
                            <Plus className="size-4" aria-hidden /> Write the first entry
                          </Button>
                        ) : undefined
                      }
                    />
                  ) : (
                    <div className="mt-5 flex flex-col gap-3">
                      {tierEntries.map((entry) => (
                        <EntryCard
                          key={entry.id}
                          entry={entry}
                          editable={isWiki}
                          onEdit={() => setEditing(entry)}
                          onDelete={() => setConfirmDelete(entry)}
                        />
                      ))}
                    </div>
                  )}
                </>
              )}
            </TabsContent>
          );
        })}
      </Tabs>

      {/* wiki editor */}
      <Dialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing?.id ? "Edit wiki entry" : "New wiki entry"}
        className="max-w-lg"
      >
        {editing && (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(
                {
                  id: editing.id,
                  tier: "wiki",
                  title: editing.title ?? "",
                  content: editing.content ?? "",
                  projectId,
                },
                {
                  onSuccess: () => {
                    setEditing(null);
                    toast({
                      title: editing.id ? "Wiki entry updated" : "Saved to wiki",
                      description: "Agents see it on the very next run.",
                      tone: "success",
                    });
                  },
                },
              );
            }}
          >
            <Input
              label="Title"
              value={editing.title ?? ""}
              onChange={(e) => setEditing((s) => ({ ...s, title: e.target.value }))}
              placeholder="Client: Meridian Skincare — context"
              required
              maxLength={120}
            />
            <Textarea
              label="Content (markdown)"
              value={editing.content ?? ""}
              onChange={(e) => setEditing((s) => ({ ...s, content: e.target.value }))}
              placeholder="Facts, preferences, constraints…"
              rows={7}
              required
            />
            <div className="flex justify-end gap-3">
              <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending}>
                {save.isPending ? "Saving…" : "Save entry"}
              </Button>
            </div>
          </form>
        )}
      </Dialog>

      {/* delete confirmation */}
      <Dialog
        open={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        title="Delete this entry?"
      >
        {confirmDelete && (
          <div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              “{confirmDelete.title}” will be removed from your wiki and agents
              stop seeing it immediately. You&apos;ll have a few seconds to undo.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
                Keep it
              </Button>
              <Button
                variant="destructive"
                loading={remove.isPending}
                onClick={() => deleteWithUndo(confirmDelete)}
              >
                Delete
              </Button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
