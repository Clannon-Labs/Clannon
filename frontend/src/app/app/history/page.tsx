"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { History as HistoryIcon, Search, Trash2 } from "lucide-react";
import { useRuns, useDeleteSession } from "@/lib/api/hooks";
import {
  useCurrentProject,
  useCurrentProjectId,
  useIsAllProjects,
} from "@/components/app/project-provider";
import { groupBySession } from "@/lib/sessions";
import { RunStatusBadge } from "@/components/app/run-status";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import type { RunStatus } from "@/lib/api";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";

const STATUS_FILTERS: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "delivered", label: "Delivered" },
  { value: "blocked", label: "Blocked" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

type DateFilter = "all" | "7d" | "30d";

const DATE_FILTERS: { value: DateFilter; label: string; days?: number }[] = [
  { value: "all", label: "Any time" },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
];

const DAY_MS = 24 * 60 * 60 * 1_000;

function FilterPill({
  selected,
  onSelect,
  children,
}: {
  selected: boolean;
  onSelect: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "cursor-pointer rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
        selected
          ? "border-primary bg-primary-soft text-primary"
          : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Every past conversation, searchable and filterable — the sidebar's own
 * "Recent" list has neither (just a flat, unlimited scroll), and this is
 * the same data (`useRuns` → `groupBySession`) it already fetches, so
 * there's no new API surface here. Scope follows the project switcher
 * (same `useCurrentProjectId` every other workspace page reads) rather
 * than duplicating that control here.
 */
export default function HistoryPage() {
  const projectId = useCurrentProjectId();
  const currentProject = useCurrentProject();
  const isAllProjects = useIsAllProjects();
  const { data: runs, isLoading } = useRuns(projectId);
  const sessions = useMemo(() => groupBySession(runs), [runs]);
  const router = useRouter();
  const pathname = usePathname();
  const toast = useToast();
  const del = useDeleteSession();

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  // Keep one reference point for this page visit. A filter should not move its
  // boundary between renders because typing in the search field took a second.
  const [filterReferenceTime] = useState(() => Date.now());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const days = DATE_FILTERS.find((filter) => filter.value === dateFilter)?.days;
    const cutoff = days ? filterReferenceTime - days * DAY_MS : null;
    return sessions.filter((session) => {
      if (status !== "all" && session.status !== status) return false;
      if (cutoff !== null && Date.parse(session.createdAt) < cutoff) return false;
      if (q && !session.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [sessions, query, status, dateFilter, filterReferenceTime]);

  function clearSelectionAnd(action: () => void) {
    setSelected(new Set());
    action();
  }

  function toggleSelected(sessionId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  async function bulkDelete() {
    const targets = filtered.filter((s) => selected.has(s.sessionId));
    setDeleting(true);
    let succeeded = 0;
    let viewingDeletedRun = false;
    // sequential, not Promise.all — one shared mutation instance, and a
    // partial failure needs an honest tally rather than an all-or-nothing
    // report of what the backend actually did.
    for (const session of targets) {
      try {
        await del.mutateAsync(session.sessionId);
        succeeded++;
        if (pathname === `/app/runs/${session.latestId}`) viewingDeletedRun = true;
      } catch {
        // tallied below — continue deleting the rest of the batch
      }
    }
    setDeleting(false);
    setConfirmBulkDelete(false);
    setSelected(new Set());
    if (succeeded === targets.length) {
      toast({
        title: `${succeeded} ${succeeded === 1 ? "conversation" : "conversations"} deleted`,
        tone: "success",
      });
    } else {
      toast({
        title: `Deleted ${succeeded} of ${targets.length} — ${targets.length - succeeded} failed`,
        tone: "warning",
      });
    }
    if (viewingDeletedRun) router.push("/app");
  }

  return (
    <div className="mx-auto max-w-4xl">
      <header>
        <p className="tag-label text-faint">
          History
          {currentProject ? ` · ${currentProject.name}` : isAllProjects ? " · All projects" : ""}
        </p>
        <h1 className="display mt-3 text-[2.4rem] leading-[1.0]">Every run</h1>
        <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
          Search by title, status, and date
          {currentProject ? ` in ${currentProject.name}` : ""}. Switch the project
          scope from the sidebar switcher.
        </p>
      </header>

      <div className="relative mt-7 max-w-sm">
        <Search
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint"
          aria-hidden
        />
        <input
          type="search"
          value={query}
          onChange={(e) => clearSelectionAnd(() => setQuery(e.target.value))}
          placeholder="Search by title…"
          aria-label="Search run history"
          className="h-10 w-full rounded-md border border-border-strong bg-surface-raised pl-10 pr-3.5 text-base text-foreground placeholder:text-faint focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 sm:text-sm"
        />
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="tag-label w-11 shrink-0 text-faint">Status</span>
          <div role="radiogroup" aria-label="Filter by status" className="flex flex-wrap gap-1.5">
            {STATUS_FILTERS.map((filter) => (
              <FilterPill
                key={filter.value}
                selected={status === filter.value}
                onSelect={() => clearSelectionAnd(() => setStatus(filter.value))}
              >
                {filter.label}
              </FilterPill>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="tag-label w-11 shrink-0 text-faint">Date</span>
          <div role="radiogroup" aria-label="Filter by date" className="flex flex-wrap gap-1.5">
            {DATE_FILTERS.map((filter) => (
              <FilterPill
                key={filter.value}
                selected={dateFilter === filter.value}
                onSelect={() => clearSelectionAnd(() => setDateFilter(filter.value))}
              >
                {filter.label}
              </FilterPill>
            ))}
          </div>
        </div>
      </div>

      {/* selection toolbar — only takes space once something is checked, so
          the common read-only path never sees it */}
      {selected.size > 0 && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border-strong bg-surface-raised px-4 py-2.5">
          <p className="text-sm font-medium text-foreground">
            {selected.size} selected
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setConfirmBulkDelete(true)}>
              <Trash2 className="size-3.5" aria-hidden /> Delete
            </Button>
          </div>
        </div>
      )}

      <div className="mt-6">
        {isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16 rounded-lg" />
            <Skeleton className="h-16 rounded-lg" />
            <Skeleton className="h-16 rounded-lg" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<HistoryIcon className="size-6" aria-hidden />}
            title={sessions.length === 0 ? "Nothing here yet" : "No matches"}
            description={
              sessions.length === 0
                ? "Runs you start will show up here, searchable and filterable."
                : "Try a different search term, status, or date filter."
            }
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {filtered.map((session) => (
              <li key={session.sessionId} className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={selected.has(session.sessionId)}
                  onChange={() => toggleSelected(session.sessionId)}
                  aria-label={`Select ${session.title}`}
                  className="size-4 shrink-0 cursor-pointer rounded border-border-strong text-primary focus:ring-2 focus:ring-ring/25"
                />
                <Link
                  href={`/app/runs/${session.latestId}`}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-border-strong hover:bg-muted"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{session.title}</p>
                    <p className="mt-1 text-[12px] text-faint tabular">
                      {formatRelativeTime(session.createdAt)} · {session.turnCount}{" "}
                      {session.turnCount === 1 ? "turn" : "turns"} · {formatTokens(session.tokensUsed)} tokens
                    </p>
                  </div>
                  <RunStatusBadge status={session.status} className="shrink-0" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Dialog
        open={confirmBulkDelete}
        onClose={() => !deleting && setConfirmBulkDelete(false)}
        title={`Delete ${selected.size} ${selected.size === 1 ? "conversation" : "conversations"}?`}
      >
        <div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {selected.size === 1 ? "It" : "They"} will be permanently removed, along
            with every turn in {selected.size === 1 ? "it" : "them"}. This can&apos;t
            be undone.
          </p>
          <div className="mt-5 flex justify-end gap-3">
            <Button variant="ghost" onClick={() => setConfirmBulkDelete(false)} disabled={deleting}>
              Keep {selected.size === 1 ? "it" : "them"}
            </Button>
            <Button variant="destructive" loading={deleting} onClick={bulkDelete}>
              Delete
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
