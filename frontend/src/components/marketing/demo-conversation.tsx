"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUp,
  Ghost,
  LineChart,
  Loader2,
  Swords,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { MockClient } from "@/lib/api/mock";
import type { DecisionLogEntry, ExpertState, RunStatus, Source } from "@/lib/api";
import { DEMO_BRIEFS, DEMO_REPORT_PREVIEW_CHARS } from "@/config/demo.config";
import { ButtonLink } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { Report } from "@/components/app/report";
import { RunStatusBadge } from "@/components/app/run-status";
import { RunActivity } from "@/components/app/run-activity";
import { UserMessage } from "@/components/app/thread";
import { Mark } from "@/components/brand/logo";
import { cn, formatTokens } from "@/lib/utils";

/** An icon per starter, in the order DEMO_BRIEFS defines them. */
const BRIEF_ICONS: LucideIcon[] = [TrendingUp, Swords, LineChart];

interface DemoState {
  status: RunStatus;
  log: DecisionLogEntry[];
  experts: ExpertState[];
  sources: Source[];
  message: string;
  reportText: string;
  reportDone: boolean;
  tokensUsed: number;
}

const EMPTY: DemoState = {
  status: "queued",
  log: [],
  experts: [],
  sources: [],
  message: "",
  reportText: "",
  reportDone: false,
  tokensUsed: 0,
};

// A soft nudge — not a gate. Canned runs cost nothing, so we never block; we
// just remind, gently, once you've watched a couple this sitting, that the real
// thing is one signup away.
const NUDGE_AFTER = 2;

/**
 * The no-signup demo, as a chat exactly like the workspace. You can't type — you
 * pick one of a few pre-defined starters and hit send, and a CANNED pipeline
 * plays out with real-looking routing, expert calls, and timing. It runs on a
 * throwaway MockClient, so it NEVER touches the backend (even in http mode) and
 * costs nothing. Same decision-log behaviour as the real run view (shared
 * RunActivity), so the demo and the product are indistinguishable in feel.
 */
export function DemoConversation() {
  const [started, setStarted] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [ranBrief, setRanBrief] = useState("");
  const [running, setRunning] = useState(false);
  const [runKey, setRunKey] = useState(0);
  const [s, setS] = useState<DemoState>(EMPTY);
  const [watched, setWatched] = useState(0);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function run(index: number) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;

    const brief = DEMO_BRIEFS[index].brief;
    setRanBrief(brief);
    setStarted(true);
    setRunning(true);
    setRunKey((k) => k + 1);
    setS(EMPTY);

    try {
      // a throwaway client — the demo is fully isolated from the real pipeline
      const client = new MockClient();
      const { id } = await client.createRun(brief);
      for await (const event of client.streamRun(id, abort.signal)) {
        setS((prev) => {
          switch (event.type) {
            case "status":
              return { ...prev, status: event.status };
            case "log":
              return { ...prev, log: [...prev.log, event.entry] };
            case "expert": {
              const idx = prev.experts.findIndex((e) => e.id === event.expert.id);
              const experts =
                idx >= 0
                  ? prev.experts.map((e, i) => (i === idx ? event.expert : e))
                  : [...prev.experts, event.expert];
              return { ...prev, experts };
            }
            case "sources":
              return { ...prev, sources: event.sources };
            case "message_delta":
              return { ...prev, message: prev.message + event.text };
            case "report_delta":
              return { ...prev, reportText: prev.reportText + event.text };
            case "report_done":
              return { ...prev, reportDone: true };
            case "usage":
              return { ...prev, tokensUsed: event.tokensUsed };
            default:
              return prev;
          }
        });
      }
    } catch {
      /* aborted (unmount or a new run started) — nothing to clean up */
    } finally {
      if (!abort.signal.aborted) {
        setRunning(false);
        setWatched((w) => w + 1);
      }
    }
  }

  const isTerminal = !running && s.reportDone;
  const preview =
    s.reportText.length > DEMO_REPORT_PREVIEW_CHARS && s.reportDone
      ? s.reportText.slice(0, DEMO_REPORT_PREVIEW_CHARS).trimEnd() + "…"
      : s.reportText;

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-3xl flex-col px-4 sm:px-6">
      <div className="flex flex-1 flex-col gap-6 pb-10 pt-6">
        {!started ? (
          /* EMPTY STATE — welcome + the pre-defined starters (pick one) */
          <div className="pt-[6vh] sm:pt-[10vh]">
            <h1 className="display flex items-center justify-center gap-2.5 text-center text-[2rem] leading-[1.1] sm:text-[2.4rem]">
              <Mark className="size-7 shrink-0 text-primary sm:size-8" aria-hidden />
              Watch Clannon work
            </h1>
            <p className="mx-auto mt-3 max-w-md text-center text-[15px] leading-relaxed text-muted-foreground">
              Pick a starter and send it. You&apos;ll see the real run — routing,
              experts working in parallel, the quality filter — start to finish.
            </p>

            <div className="mt-8 grid gap-2.5 sm:grid-cols-3 sm:gap-3">
              {DEMO_BRIEFS.map((brief, i) => {
                const Icon = BRIEF_ICONS[i] ?? TrendingUp;
                const active = selected === i;
                return (
                  <button
                    key={brief.label}
                    type="button"
                    onClick={() => setSelected(i)}
                    aria-pressed={active}
                    className={cn(
                      "flex items-center gap-3.5 rounded-2xl border p-4 text-left transition-colors sm:flex-col sm:items-start sm:gap-2.5 sm:rounded-xl",
                      active
                        ? "border-primary bg-primary-soft"
                        : "border-border bg-surface hover:border-border-strong hover:bg-muted",
                    )}
                  >
                    <Icon className={cn("size-5 shrink-0", active ? "text-primary" : "text-primary/70")} aria-hidden />
                    <span className="text-sm font-medium leading-snug text-foreground sm:text-[13px]">
                      {brief.label}
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="mt-4 text-center text-[12px] text-faint">
              {selected === null ? "Select one, then press send below." : "Ready — press send below."}
            </p>

            {/* the anatomy of a run, in the ledger's own language — so the
                empty screen teaches what the decision log is about to show */}
            <div className="mx-auto mt-12 max-w-md" aria-hidden>
              <p className="tag-label text-center text-faint">What you&apos;ll watch</p>
              <div className="mt-3 rounded-lg border border-border bg-surface px-5 py-3">
                {/* one spine, drawn tick-to-tick — no dangling segment above the
                    first entry or below the last */}
                <div className="relative">
                  <span
                    aria-hidden
                    className="absolute bottom-[17px] left-0 top-[17px] w-px bg-border"
                  />
                  {(
                    [
                      { label: "MEM", dot: "bg-log-memory", ink: "text-log-memory", copy: "context loads before planning starts" },
                      { label: "ROUTE", dot: "bg-log-route", ink: "text-log-route", copy: "the brief splits into domains" },
                      { label: "EXPERT", dot: "bg-log-expert", ink: "text-log-expert", copy: "specialists work in parallel" },
                      { label: "ANSWER", dot: "bg-log-answer", ink: "text-foreground", copy: "a filtered report lands" },
                    ] as const
                  ).map((row) => (
                    <div key={row.label} className="relative py-2 pl-4">
                      <span
                        className={cn("absolute -left-[4px] top-[13px] size-[9px] rounded-full ring-4 ring-surface", row.dot)}
                      />
                      <span className="flex items-baseline gap-3">
                        <span className={cn("w-14 shrink-0 font-mono text-[10px] font-semibold uppercase tracking-[0.16em]", row.ink)}>
                          {row.label}
                        </span>
                        <span className="text-[12px] text-muted-foreground">{row.copy}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* TRANSCRIPT — a chat turn, exactly like the workspace run view */
          <div className="flex flex-col gap-6">
            <div className="flex flex-col items-end gap-1.5">
              <UserMessage>{ranBrief}</UserMessage>
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <span className="flex items-center gap-2">
                  <Mark className="size-5 text-primary" aria-hidden />
                  <span className="font-display text-[15px] font-medium">Clannon</span>
                </span>
                {isTerminal && <RunStatusBadge status={s.status} />}
                {s.tokensUsed > 0 && (
                  <span className="text-[12px] text-faint tabular">
                    {formatTokens(s.tokensUsed)} tokens
                  </span>
                )}
                <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-faint">
                  <Ghost className="size-3" aria-hidden /> Demo · not saved
                </span>
              </div>

              {/* the agent talking — streamed commentary, like the real run */}
              {s.message && (
                <div className="mt-3">
                  <Report markdown={s.message} streaming={running && !s.reportDone} />
                </div>
              )}

              {/* the work — collapsed by default, identical to the workspace */}
              <RunActivity
                log={s.log}
                status={s.status}
                experts={s.experts}
                sources={s.sources}
                live={running}
                isTerminal={isTerminal}
                resetKey={String(runKey)}
              />

              {/* the report — buffered, arrives after the filter passes */}
              {s.reportText && (
                <section aria-label="Report" className="mt-6 rounded-lg border border-border bg-surface">
                  <header className="flex items-center justify-between border-b border-border px-5 py-3.5 sm:px-8">
                    <h2 className="tag-label text-muted-foreground">
                      {s.reportDone ? "Report — passed output filter" : "Report — streaming"}
                    </h2>
                    {s.reportDone && <span className="tag-label text-primary">Verified</span>}
                  </header>
                  <div className="px-5 py-6 sm:px-8 sm:py-8">
                    <Report markdown={preview} streaming={!s.reportDone} ornate={s.reportDone} />
                  </div>
                </section>
              )}

              {/* conversion — the demo stops where memory would begin */}
              {s.reportDone && (
                <div className="mt-6 rounded-xl border border-primary/30 bg-primary-soft/50 p-6 text-center sm:p-8">
                  <p className="display-soft text-[1.4rem] leading-tight">
                    Sign up and it never forgets this.
                  </p>
                  <p className="mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-muted-foreground">
                    The demo runs clean every time but starts from zero. The real
                    Clannon carries your clients, your style, and what worked last
                    time into every run.
                  </p>
                  <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
                    <ButtonLink href="/signup">
                      Start free <ArrowRight className="size-4" aria-hidden />
                    </ButtonLink>
                    <button
                      type="button"
                      onClick={() => {
                        controller.current?.abort();
                        setStarted(false);
                        setSelected(null);
                        setRunning(false);
                        setS(EMPTY);
                      }}
                      className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-4 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                    >
                      Watch another
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* the composer — preset only. Looks like the workspace, but you select
          a starter instead of typing (a free demo of the real pipeline would be
          a great way to go bankrupt). */}
      <div className="composer-scrim sticky bottom-0 z-30 border-t border-border bg-background/95 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 backdrop-blur-md">
        {watched >= NUDGE_AFTER && (
          <div className="mb-2 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 rounded-lg border border-primary/25 bg-primary-soft/40 px-3 py-2 text-center text-[12px] text-muted-foreground">
            <span>You&apos;ve watched {watched} runs — the real one would remember every one.</span>
            <Link href="/signup" className="font-medium text-primary underline-offset-2 hover:underline">
              Run your own, free →
            </Link>
          </div>
        )}
        {started && (
          <div className="mb-2 flex gap-2 overflow-x-auto pb-0.5">
            {DEMO_BRIEFS.map((brief, i) => (
              <button
                key={brief.label}
                type="button"
                disabled={running}
                onClick={() => setSelected(i)}
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1.5 text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                  selected === i
                    ? "border-primary bg-primary-soft text-primary"
                    : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
                )}
              >
                {brief.label}
              </button>
            ))}
          </div>
        )}

        <div
          className={cn(
            "flex items-center gap-2 rounded-3xl border bg-surface-raised px-5 py-4 transition-colors sm:px-4 sm:py-3.5",
            selected !== null ? "border-border-strong" : "border-border",
          )}
        >
          <p
            className={cn(
              "min-w-0 flex-1 truncate text-[15px]",
              selected !== null ? "text-foreground" : "text-faint",
            )}
          >
            {selected !== null
              ? DEMO_BRIEFS[selected].brief
              : "Pick a starter — you can't type in the demo, but you'll see a real run."}
          </p>
          <Tooltip label={selected === null ? "Pick a starter first" : "Send"} align="end">
            <button
              type="button"
              onClick={() => selected !== null && run(selected)}
              disabled={selected === null || running}
              aria-label="Send the selected starter"
              className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40 sm:size-9"
            >
              {running ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <ArrowUp className="size-4" aria-hidden />
              )}
            </button>
          </Tooltip>
        </div>
        <p className="mt-1.5 text-center text-[11px] text-faint">
          A canned run — no signup, no memory, no cost.{" "}
          <Link href="/signup" className="text-primary underline-offset-2 hover:underline">
            Sign up
          </Link>{" "}
          to run your own brief.
        </p>
      </div>
    </div>
  );
}
