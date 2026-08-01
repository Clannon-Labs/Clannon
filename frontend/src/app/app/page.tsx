"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { FolderPlus, Target } from "lucide-react";
import {
  useBudgetExhausted,
  useCreateRun,
  useMe,
  useMemoryEntries,
  useProjects,
  useRuns,
  useUsage,
} from "@/lib/api/hooks";
import {
  useCreateProjectDialog,
  useCurrentProjectId,
} from "@/components/app/project-provider";
import { ApiError } from "@/lib/api";
import { Mark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Composer } from "@/components/app/composer";
import { HydrationPanel } from "@/components/app/hydration-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";
import { workspaceDraftKey } from "@/lib/browser-drafts";
import { useBrowserTextDraft } from "@/lib/use-browser-draft";
import { findGoalEntry } from "@/lib/project-goal";
import { cn } from "@/lib/utils";

// Greetings that read fine in front of ", <name>" (and standalone, when there's
// no name). Time-aware lines respect the clock; the rest are just for fun.
const ANYTIME_GREETINGS = [
  "Welcome back",
  "Look who's back",
  "Back at it",
  "Good to see you",
  "Ready when you are",
  "Let's make something good",
  "The archive missed you",
  "Fancy seeing you here",
  "Let's get into it",
  "Right on time",
  "There you are",
  "Let's dig in",
];

function timeGreetings(hour: number): string[] {
  if (hour < 5) return ["Burning the midnight oil", "Still up", "Working the night shift"];
  if (hour < 8) return ["Up with the sun", "Bright and early", "Good morning"];
  if (hour < 12) return ["Good morning", "Morning", "Rise and grind"];
  if (hour < 17) return ["Good afternoon", "Afternoon"];
  if (hour < 21) return ["Good evening", "Evening"];
  return ["Good evening", "Winding down for the night", "One more before bed"];
}

/**
 * A greeting for the new-chat screen — different (mostly) each call. Time-of-day
 * lines are kept honest to the clock; everything else is just for flavour. Called
 * once per page load (see `greet` below) so it doesn't reshuffle as you type.
 * Client-only (the page renders behind the auth gate), so `new Date()` is safe.
 */
function greeting(): string {
  const pool = [...timeGreetings(new Date().getHours()), ...ANYTIME_GREETINGS];
  return pool[Math.floor(Math.random() * pool.length)];
}

const GREETING_KEY = "clannon.greeting";
const GREETING_MAX_AGE = 30 * 60 * 1000; // reshuffle after 30 min, or a new session

/**
 * Pick a greeting but keep it stable across refreshes — it only reshuffles when
 * you come back later (a fresh tab session clears sessionStorage) or after 30
 * minutes. Cheap, and stops the line flickering on every reload.
 */
function pickGreeting(): string {
  if (typeof window === "undefined") return greeting();
  try {
    const raw = sessionStorage.getItem(GREETING_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as { value: string; ts: number };
      if (saved.value && Date.now() - saved.ts < GREETING_MAX_AGE) return saved.value;
    }
  } catch {
    /* storage unavailable — just pick a fresh one */
  }
  const value = greeting();
  try {
    sessionStorage.setItem(GREETING_KEY, JSON.stringify({ value, ts: Date.now() }));
  } catch {
    /* ignore */
  }
  return value;
}

export default function WorkspacePage() {
  const router = useRouter();
  const { data: user } = useMe();
  const projectId = useCurrentProjectId();
  const { data: runs } = useRuns(projectId);
  const { data: projects } = useProjects();
  // set once at project creation, in the New Project dialog — pinned here so
  // "why am I working on this" stays in view instead of waiting in the
  // Memory tab until you go looking for it
  const { data: memoryEntries } = useMemoryEntries(projectId);
  const goal = findGoalEntry(memoryEntries);
  const createRun = useCreateRun();
  const budgetExhausted = useBudgetExhausted();
  const { data: budgetUsage } = useUsage();
  const { openDialog: openCreateProject } = useCreateProjectDialog();
  const [error, setError] = useState<string | ApiError | null>(null);
  const draftKey = user?.id ? workspaceDraftKey(user.id, projectId) : null;
  const [brief, setBrief] = useBrowserTextDraft(draftKey);
  // pick a greeting once per load (re-rendering on every keystroke must not reshuffle it)
  const [greet] = useState(pickGreeting);

  const firstName = user?.name.split(" ")[0] ?? "";
  const isFirstRun = runs?.length === 0;
  const workspaceReady = Boolean(user) && runs !== undefined;
  // the "create your first project" nudge — only when there's truly no
  // project yet (a user who already has one, even with zero runs, has
  // already given that context; nudging them to make a redundant "first"
  // one would be wrong, not just repetitive). Recedes once typing starts,
  // same reasoning as the old first-run form: don't clutter mid-brief.
  const showFirstRunCta =
    workspaceReady && isFirstRun && projects?.length === 0 && !brief.trim();
  // "Welcome back"/"Look who's back"/"The archive missed you" are all false
  // on a genuinely first visit — there's nothing to come back to yet. Gate on
  // !workspaceReady too: `runs` starts undefined while the query is in
  // flight, so `isFirstRun` is briefly false for everyone, and without this
  // a first-timer would flash "Welcome back" for the loading window before
  // it flips. A first run only happens once, so it doesn't need the pool.
  const displayGreet = !workspaceReady || isFirstRun ? "Welcome" : greet;

  return (
    /* the new-chat screen — laid out like a run (and the demo): a centered
       hero, starter cards, the hydration moment, then a docked composer that
       carries the full control set (model picker, attach). History is in the
       sidebar, not here. */
    <div className="mx-auto flex min-h-[calc(100dvh-7rem)] max-w-3xl flex-col md:min-h-[calc(100dvh-4rem)]">
      {/* while a brief is being typed the recap recedes to a chip and the
          block is short — centre it so the space above the composer reads as
          intentional breathing room, not a dead void. At rest (tall recap) the
          content fills the column and centring is a no-op. */}
      <div className={cn("flex flex-1 flex-col pb-10", brief.trim() && "justify-center")}>
        <div className="pt-[3vh] sm:pt-[10vh]">
          <h1 className="display flex items-center justify-center gap-2.5 text-center text-[2.15rem] leading-[1.1] sm:text-[2.6rem]">
            <Mark className="size-7 shrink-0 text-primary sm:size-8" aria-hidden />
            <span>
              {displayGreet}
              {firstName && (
                <>
                  {", "}
                  <span className="capitalize">{firstName}</span>
                </>
              )}
            </span>
          </h1>
          <p className="mx-auto mt-4 max-w-md text-center text-[15px] leading-relaxed text-muted-foreground">
            Describe the work. I&apos;ll route it, run the research in parallel, and
            bring back something verified — carrying what I remember about your clients.
          </p>
          {/* pinned, not part of the recap below — stays put whether you're
              typing or not, same as the greeting above it */}
          {goal && (
            <div className="mx-auto mt-5 flex max-w-md items-start gap-2.5 rounded-lg border border-border bg-surface px-4 py-3 text-left">
              <Target className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
              <div className="min-w-0">
                <p className="tag-label text-faint">Goal</p>
                <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-foreground">
                  {goal.content}
                </p>
              </div>
            </div>
          )}
        </div>

        {!workspaceReady ? (
          <div role="status" aria-label="Loading workspace" className="mt-10 grid gap-3">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
          </div>
        ) : (
          <>
            {showFirstRunCta && (
              /* nudge, not a gate — a first-timer can just start typing below.
                 The actual name/goal/context/files form lives in the New
                 Project dialog this opens, triggered by a click, not shown
                 by default (owner correction, 2026-08-01: those fields were
                 previously ambient on this screen with no click needed). */
              <div className="mt-7 flex flex-col items-start gap-3 rounded-2xl border border-border-strong bg-surface p-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">
                    Start with a project
                  </p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">
                    Give Clannon a name, the goal, and any context or files up front —
                    every run in it starts already knowing your client.
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={openCreateProject} className="shrink-0">
                  <FolderPlus className="size-4" aria-hidden /> Create your first project
                </Button>
              </div>
            )}

            {/* starter cards — clicking loads the full brief into the composer.
                Compact rows on a phone, full cards on a wider screen. */}
            <div className="mt-7 grid gap-2.5 sm:mt-10 sm:grid-cols-3 sm:gap-3">
              {EXAMPLE_BRIEFS.map((example) => (
                <button
                  key={example.label}
                  type="button"
                  onClick={() => setBrief(example.brief)}
                  className="group flex items-center gap-3.5 rounded-2xl border border-border bg-surface p-4 text-left transition-colors hover:border-border-strong hover:bg-muted sm:flex-col sm:items-start sm:gap-2.5 sm:rounded-xl"
                >
                  <example.icon
                    className="size-5 shrink-0 text-primary/70 transition-colors group-hover:text-primary"
                    aria-hidden
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm font-medium leading-snug text-foreground sm:text-[13px]">
                      {example.label}
                    </span>
                    <span className="mt-0.5 text-[12px] leading-snug text-muted-foreground sm:mt-0">
                      {example.hint}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            {/* the hydration moment — context surfaces before the brief is even sent */}
            <HydrationPanel brief={brief} projectId={projectId} className="mt-8 sm:mt-12" />
          </>
        )}
      </div>

      {workspaceReady && (
        /* docked composer — same control set as the run reply, same place too */
        <div className="composer-scrim sticky bottom-0 z-30 border-t border-border bg-background pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3">
          <Composer
            value={brief}
            onChange={setBrief}
            pending={createRun.isPending}
            submitError={error}
            budgetExhausted={budgetExhausted}
            budgetUsage={budgetUsage}
            rows={1}
            placeholder="How can I help you today?"
            onSubmit={(files, models) => {
              setError(null);
              createRun.mutate(
                { brief, files, models, projectId },
                {
                  onSuccess: ({ id }) => {
                    setBrief("");
                    router.push(`/app/runs/${id}`);
                  },
                  onError: (err) => setError(
                    err instanceof ApiError ? err : "Could not start the run — try again.",
                  ),
                },
              );
            }}
          />
        </div>
      )}
    </div>
  );
}
