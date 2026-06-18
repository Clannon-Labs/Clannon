"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCreateRun, useMe } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Mark } from "@/components/brand/logo";
import { Composer } from "@/components/app/composer";
import { HydrationPanel } from "@/components/app/hydration-panel";
import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";

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
  const createRun = useCreateRun();
  const [brief, setBrief] = useState("");
  const [error, setError] = useState<string | null>(null);
  // pick a greeting once per load (re-rendering on every keystroke must not reshuffle it)
  const [greet] = useState(pickGreeting);

  const firstName = user?.name.split(" ")[0] ?? "";

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      {/* the new-chat screen — greeting, composer, prompts, then the hydration
          moment (our signature). History lives in the sidebar, not here. */}
      <div className="pt-[7vh] sm:pt-[11vh]">
        <h1 className="display flex items-center justify-center gap-2.5 text-center text-[2rem] leading-[1.1] sm:text-[2.6rem]">
          <Mark className="size-7 shrink-0 text-primary sm:size-8" aria-hidden />
          <span>
            {greet}
            {firstName && (
              <>
                {", "}
                <span className="capitalize">{firstName}</span>
              </>
            )}
          </span>
        </h1>

        <Composer
          className="mt-7"
          value={brief}
          onChange={setBrief}
          pending={createRun.isPending}
          submitError={error}
          rows={3}
          placeholder="How can I help you today?"
          onSubmit={(files, models) => {
            setError(null);
            createRun.mutate(
              { brief, files, models },
              {
                onSuccess: ({ id }) => router.push(`/app/runs/${id}`),
                onError: (err) =>
                  setError(
                    err instanceof ApiError ? err.message : "Could not start the run — try again.",
                  ),
              },
            );
          }}
        />

        {/* suggestion chips — clicking drops the full brief into the composer */}
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {EXAMPLE_BRIEFS.map((example) => (
            <button
              key={example.label}
              type="button"
              onClick={() => setBrief(example.brief)}
              title={example.hint}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3.5 py-2 text-[13px] text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
            >
              <example.icon className="size-3.5 text-primary/70" aria-hidden />
              {example.label}
            </button>
          ))}
        </div>
      </div>

      {/* the hydration moment — context surfaces before the brief is even sent */}
      <HydrationPanel brief={brief} className="mt-14" />
    </div>
  );
}
