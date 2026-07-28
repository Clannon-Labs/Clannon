interface DemoEntry {
  kind: "MEM" | "ROUTE" | "EXPERT" | "TOOL" | "OBS" | "ANSWER";
  time: string;
  text: string;
  detail: string;
  dot: string;
}

const ENTRIES: DemoEntry[] = [
  {
    kind: "MEM",
    time: "00:01.2",
    text: "memory hydrated",
    detail: "2 wiki · 3 episodic · 1.9k tokens",
    dot: "bg-log-memory",
  },
  {
    kind: "ROUTE",
    time: "00:02.8",
    text: "brief routed → 3 domains",
    detail: "market · regulatory · competitive",
    dot: "bg-log-route",
  },
  {
    kind: "EXPERT",
    time: "00:03.4",
    text: "3 specialists working in parallel",
    detail: "market · regulation · competition",
    dot: "bg-log-expert",
  },
  {
    kind: "TOOL",
    time: "00:05.9",
    text: "web_search “UK skincare market 2026”",
    detail: "8 results",
    dot: "bg-log-tool",
  },
  {
    kind: "OBS",
    time: "00:11.4",
    text: "figures conflict (£3.1B vs £3.4B)",
    detail: "recency check triggered",
    dot: "bg-faint",
  },
  {
    kind: "ANSWER",
    time: "00:21.3",
    text: "draft assembled · 1,900 words",
    detail: "entering output filter",
    dot: "bg-log-answer",
  },
];

/**
 * Product proof without client hydration. Rows ink in once through compositor
 * CSS, preserving live-ledger feel while keeping landing JavaScript off main
 * thread.
 */
export function HeroDemo() {
  return (
    <div aria-hidden className="dark relative overflow-hidden rounded-xl border border-border bg-background p-1">
      <div className="rounded-[10px] bg-surface">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="size-2 animate-pulse-dot rounded-full bg-primary" />
            <span className="tag-label text-muted-foreground">decision log — live</span>
          </div>
          <span className="tag-label hidden text-faint sm:block">run_4c2a · 3 experts</span>
        </div>

        <div className="scroll-fade-x flex h-[280px] flex-col justify-end gap-0.5 overflow-hidden py-3 pl-4 pr-0 font-mono text-[13px] leading-relaxed sm:h-[300px]">
          {ENTRIES.map((entry, index) => (
            <div
              key={entry.time}
              className="hero-ledger-row flex items-baseline gap-2.5 py-[3px]"
              style={{ animationDelay: `${160 + index * 180}ms` }}
            >
              <span className="hidden shrink-0 text-faint sm:inline">{entry.time}</span>
              <span className="flex shrink-0 items-center gap-1.5">
                <span className={`inline-block size-1.5 rounded-full ${entry.dot}`} />
                <span className="w-14 text-[11px] tracking-wider text-muted-foreground">
                  {entry.kind}
                </span>
              </span>
              <span className="whitespace-nowrap text-foreground">
                {entry.text}
                <span className="ml-2 hidden text-faint md:inline">· {entry.detail}</span>
              </span>
            </div>
          ))}
          <div
            className="hero-ledger-row flex items-center gap-2 border-t border-border pt-2 text-primary"
            style={{ animationDelay: "1400ms" }}
          >
            <span className="inline-block size-1.5 animate-pulse-dot rounded-full bg-primary" />
            <span>quality-checking every material claim…</span>
          </div>
        </div>
      </div>
    </div>
  );
}
