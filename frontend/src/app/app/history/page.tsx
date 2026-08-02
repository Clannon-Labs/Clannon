"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { History as HistoryIcon, Search } from "lucide-react";
import { useRuns } from "@/lib/api/hooks";
import {
  useCurrentProject,
  useCurrentProjectId,
  useIsAllProjects,
} from "@/components/app/project-provider";
import { groupBySession } from "@/lib/sessions";
import { RunStatusBadge } from "@/components/app/run-status";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import type { RunStatus } from "@/lib/api";
import { cn, formatRelativeTime, formatTokens } from "@/lib/utils";

const STATUS_FILTERS: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "delivered", label: "Delivered" },
  { value: "blocked", label: "Blocked" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

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

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<RunStatus | "all">("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sessions.filter((session) => {
      if (status !== "all" && session.status !== status) return false;
      if (q && !session.title.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [sessions, query, status]);

  return (
    <div className="mx-auto max-w-4xl">
      <header>
        <p className="tag-label text-faint">
          History
          {currentProject ? ` · ${currentProject.name}` : isAllProjects ? " · All projects" : ""}
        </p>
        <h1 className="display mt-3 text-[2.4rem] leading-[1.0]">Every run</h1>
        <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
          Search and filter past conversations
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
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by title…"
          aria-label="Search run history"
          className="h-10 w-full rounded-md border border-border-strong bg-surface-raised pl-10 pr-3.5 text-base text-foreground placeholder:text-faint focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/25 sm:text-sm"
        />
      </div>

      <div role="radiogroup" aria-label="Filter by status" className="mt-4 flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            role="radio"
            aria-checked={status === f.value}
            onClick={() => setStatus(f.value)}
            className={cn(
              "cursor-pointer rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
              status === f.value
                ? "border-primary bg-primary-soft text-primary"
                : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

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
                : "Try a different search term or status filter."
            }
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {filtered.map((session) => (
              <li key={session.sessionId}>
                <Link
                  href={`/app/runs/${session.latestId}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 transition-colors hover:border-border-strong hover:bg-muted"
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
    </div>
  );
}
