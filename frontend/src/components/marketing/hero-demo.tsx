"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface DemoEntry {
  kind: "hydration" | "route" | "expert_spawn" | "tool_call" | "observation" | "answer";
  time: string;
  text: string;
  detail?: string;
}

const SCRIPT: DemoEntry[] = [
  { kind: "hydration", time: "00:01.2", text: "memory hydrated", detail: "2 wiki · 3 episodic · 1.9k tokens" },
  { kind: "route", time: "00:02.8", text: "brief routed → 3 domains", detail: "market · regulatory · competitive" },
  { kind: "expert_spawn", time: "00:03.1", text: "spawn web.research/market" },
  { kind: "expert_spawn", time: "00:03.4", text: "spawn web.research/regulatory" },
  { kind: "expert_spawn", time: "00:03.6", text: "spawn web.research/competitive" },
  { kind: "tool_call", time: "00:05.9", text: "web_search “UK skincare market 2026”", detail: "8 results" },
  { kind: "tool_call", time: "00:07.2", text: "fetch_url gov.uk/cosmetics-guidance", detail: "re-sanitized · clean" },
  { kind: "observation", time: "00:11.4", text: "figures conflict (£3.1B vs £3.4B)", detail: "recency check triggered" },
  { kind: "observation", time: "00:14.0", text: "regulatory expert → summary", detail: "210 tokens to orchestrator" },
  { kind: "observation", time: "00:16.8", text: "market expert → summary", detail: "188 tokens to orchestrator" },
  { kind: "answer", time: "00:21.3", text: "draft assembled · 1,900 words", detail: "buffering through output filter" },
];

const KIND_STYLE: Record<DemoEntry["kind"], { dot: string; label: string }> = {
  hydration: { dot: "bg-log-memory", label: "MEM" },
  route: { dot: "bg-log-route", label: "ROUTE" },
  expert_spawn: { dot: "bg-log-expert", label: "EXPERT" },
  tool_call: { dot: "bg-log-tool", label: "TOOL" },
  observation: { dot: "bg-faint", label: "OBS" },
  answer: { dot: "bg-log-answer", label: "ANSWER" },
};

const VISIBLE = 6;

/**
 * A dark workspace island on the paper page — the orchestrator's
 * decision log, playing on loop. Shows the actual product instead
 * of describing it.
 */
export function HeroDemo() {
  const [count, setCount] = useState(2);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let current = 2;
    const tick = () => {
      if (reduceMotion) {
        setCount(SCRIPT.length);
        return;
      }
      current = current >= SCRIPT.length ? 2 : current + 1;
      setCount(current);
      timer.current = setTimeout(
        tick,
        current >= SCRIPT.length ? 2600 : 760 + Math.random() * 700,
      );
    };
    timer.current = setTimeout(tick, reduceMotion ? 0 : 900);
    return () => clearTimeout(timer.current);
  }, []);

  const entries = SCRIPT.slice(Math.max(0, count - VISIBLE), count);
  const done = count >= SCRIPT.length;

  return (
    <div
      aria-hidden
      className="dark relative overflow-hidden rounded-xl border border-border bg-background p-1"
    >
      <div className="rounded-[10px] bg-surface">
        {/* title bar */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className={cn("size-2 rounded-full", done ? "bg-primary" : "animate-pulse-dot bg-primary")} />
            <span className="tag-label text-muted-foreground">decision log — live</span>
          </div>
          <span className="tag-label hidden text-faint sm:block">run_4c2a · 3 experts</span>
        </div>

        {/* log body — unfilled lines render as ghost rules (ledger paper
            waiting to be written) so the card is never half empty. The body
            (not each row) carries the right-edge fade: masking the container
            is reliable where masking an inline row is not. */}
        <div className="scroll-fade-x flex h-[280px] flex-col justify-end gap-0.5 overflow-hidden py-3 pl-4 pr-0 font-mono text-[13px] leading-relaxed sm:h-[300px]">
          {/* unwritten rules — faint dotted leaders so the card is never
              half-empty, reading as ledger paper waiting, not broken data */}
          {Array.from({ length: Math.max(0, 8 - entries.length) }).map((_, i) => (
            <div key={`ghost-${i}`} aria-hidden className="flex items-center py-[3px]">
              <span className="h-px flex-1 border-t border-dotted border-border/70" />
            </div>
          ))}
          {entries.map((entry, i) => {
            const style = KIND_STYLE[entry.kind];
            return (
              <div
                key={`${entry.time}-${i}`}
                className={cn(
                  "flex items-baseline gap-2.5 py-[3px]",
                  i === entries.length - 1 && "animate-log-in",
                )}
              >
                <span className="hidden shrink-0 text-faint sm:inline">{entry.time}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <span className={cn("inline-block size-1.5 rounded-full", style.dot)} />
                  <span className="w-14 text-[11px] tracking-wider text-muted-foreground">
                    {style.label}
                  </span>
                </span>
                {/* nowrap so the row runs off the right edge and the body's
                    scroll-fade-x dissolves it — never a hard mid-word clip */}
                <span className="whitespace-nowrap text-foreground">
                  {entry.text}
                  {entry.detail && (
                    <span className="ml-2 hidden text-faint md:inline">· {entry.detail}</span>
                  )}
                </span>
              </div>
            );
          })}
          {!done && (
            <div className="flex items-center gap-2 py-[3px] text-faint">
              <span className="animate-pulse-dot inline-block size-1.5 rounded-full bg-faint" />
              <span>orchestrating…</span>
            </div>
          )}
          {done && (
            <div className="animate-log-in mt-1 flex items-center gap-2 border-t border-border pt-2 text-primary">
              <span className="inline-block size-1.5 rounded-full bg-primary" />
              <span>report delivered — 6 sources · output filter passed</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
