"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ArrowRight, Sprout } from "lucide-react";
import { useCreateRun, useMe, useRuns } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton, EmptyState } from "@/components/ui/skeleton";
import { RunStatusBadge } from "@/components/app/run-status";
import { HydrationPanel } from "@/components/app/hydration-panel";
import { formatRelativeTime, formatTokens } from "@/lib/utils";

import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";
import { appConfig } from "@/config/app.config";

export default function WorkspacePage() {
  const router = useRouter();
  const { data: user } = useMe();
  const { data: runs, isLoading } = useRuns();
  const createRun = useCreateRun();
  const [brief, setBrief] = useState("");
  const [error, setError] = useState<string | null>(null);

  const firstName = user?.name.split(" ")[0] ?? "";

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createRun.mutate(brief, {
      onSuccess: ({ id }) => router.push(`/app/runs/${id}`),
      onError: (err) =>
        setError(err instanceof ApiError ? err.message : "Could not start the run — try again."),
    });
  }

  return (
    <div className="mx-auto max-w-4xl">
      <header>
        <p className="tag-label text-faint">Workspace</p>
        <h1 className="display mt-3 text-[2.4rem] leading-[1.0] sm:text-[3rem]">
          What are we researching
          {firstName ? (
            <>
              , <span className="capitalize text-primary">{firstName}</span>?
            </>
          ) : (
            "?"
          )}
        </h1>
      </header>

      {/* brief composer */}
      <form onSubmit={onSubmit} className="mt-8">
        <div className="overflow-hidden rounded-lg border border-border-strong bg-surface transition-colors focus-within:border-primary">
          <label htmlFor="brief" className="sr-only">
            Research brief
          </label>
          <textarea
            id="brief"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="Paste the client brief — raw notes are fine. The pipeline will figure out what it needs…"
            rows={5}
            className="w-full resize-none bg-transparent px-5 py-4 text-[15px] leading-relaxed placeholder:text-faint focus:outline-none"
          />
          <div className="flex flex-col gap-3 border-t border-border bg-background/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[12px] text-faint">
              Memory loads automatically · every decision is streamed live ·{" "}
              <kbd className="rounded border border-border px-1 font-mono text-[11px]">⌘↵</kbd> to run
            </p>
            <Button
              type="submit"
              loading={createRun.isPending}
              disabled={brief.trim().length < appConfig.limits.briefMinChars}
            >
              {createRun.isPending ? "Entering pipeline…" : "Run research"}
              {!createRun.isPending && <ArrowRight className="size-4" aria-hidden />}
            </Button>
          </div>
        </div>
        {error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {error}
          </p>
        )}
      </form>

      {/* example briefs */}
      <div className="mt-4 flex flex-wrap gap-2">
        {EXAMPLE_BRIEFS.map((example) => (
          <button
            key={example.slice(0, 24)}
            type="button"
            onClick={() => setBrief(example)}
            className="cursor-pointer rounded-full border border-border bg-surface px-3.5 py-1.5 text-left text-[12.5px] text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
          >
            {example.split(":")[0].split(".")[0]}
          </button>
        ))}
      </div>

      {/* the hydration moment — context surfaces before the brief is even sent */}
      <HydrationPanel brief={brief} className="mt-8" />

      {/* recent runs */}
      <section className="mt-14" aria-label="Recent runs">
        <div className="flex items-baseline justify-between">
          <h2 className="tag-label text-faint">Recent runs</h2>
        </div>

        {isLoading ? (
          <div className="mt-4 flex flex-col gap-2">
            <Skeleton className="h-[72px]" />
            <Skeleton className="h-[72px]" />
            <Skeleton className="h-[72px]" />
          </div>
        ) : !runs || runs.length === 0 ? (
          <EmptyState
            className="mt-4"
            icon={<Sprout className="size-8" aria-hidden />}
            title="Nothing planted yet"
            description="Run your first brief above. Every run becomes a ring in your archive — searchable, citable, remembered."
          />
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
            {runs.map((run) => (
              <li key={run.id}>
                <Link
                  href={`/app/runs/${run.id}`}
                  className="group flex items-center justify-between gap-4 rounded-lg border border-border bg-surface px-5 py-4 transition-colors hover:border-border-strong hover:bg-surface-raised"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-medium group-hover:text-primary">
                      {run.title}
                    </p>
                    <p className="mt-1 text-[12.5px] text-faint tabular">
                      {formatRelativeTime(run.createdAt)}
                      {run.expertCount > 0 && <> · {run.expertCount} experts</>}
                      {run.tokensUsed > 0 && <> · {formatTokens(run.tokensUsed)} tokens</>}
                    </p>
                  </div>
                  <RunStatusBadge status={run.status} className="shrink-0" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
