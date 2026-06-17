"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useCreateRun, useMe } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api";
import { Mark } from "@/components/brand/logo";
import { Composer } from "@/components/app/composer";
import { HydrationPanel } from "@/components/app/hydration-panel";
import { WORKSPACE_EXAMPLES as EXAMPLE_BRIEFS } from "@/config/demo.config";

/** Time-of-day greeting, like Claude's "Good evening". Client-only (the page
 *  renders behind the auth gate), so `new Date()` won't cause a hydration skew. */
function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function WorkspacePage() {
  const router = useRouter();
  const { data: user } = useMe();
  const createRun = useCreateRun();
  const [brief, setBrief] = useState("");
  const [error, setError] = useState<string | null>(null);

  const firstName = user?.name.split(" ")[0] ?? "";

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      {/* the new-chat screen — greeting, composer, prompts, then the hydration
          moment (our signature). History lives in the sidebar, not here. */}
      <div className="pt-[7vh] sm:pt-[11vh]">
        <h1 className="display flex items-center justify-center gap-2.5 text-center text-[2rem] leading-[1.1] sm:text-[2.6rem]">
          <Mark className="size-7 shrink-0 text-primary sm:size-8" aria-hidden />
          <span>
            {greeting()}
            {firstName && (
              <>
                , <span className="capitalize">{firstName}</span>
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
