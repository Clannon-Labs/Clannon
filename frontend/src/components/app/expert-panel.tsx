import { ExternalLink } from "lucide-react";
import { normalizeHttpUrl } from "@/config/url-policy";
import type { ExpertState, Source } from "@/lib/api";
import { cn } from "@/lib/utils";

const EXPERT_STATUS: Record<ExpertState["status"], { label: string; tone: string; live?: boolean }> = {
  spawned: { label: "Spawned", tone: "text-log-expert", live: true },
  working: { label: "Working", tone: "text-primary", live: true },
  summarizing: { label: "Summarizing", tone: "text-memory", live: true },
  done: { label: "Done", tone: "text-muted-foreground" },
  failed: { label: "Failed", tone: "text-destructive" },
};

export function ExpertPanel({ experts, className }: { experts: ExpertState[]; className?: string }) {
  return (
    <section
      aria-label="Experts"
      className={cn("rounded-lg border border-border bg-surface", className)}
    >
      <header className="px-4 pt-3.5">
        <div className="flex items-baseline justify-between">
          <h2 className="display-soft text-[15px] leading-none text-foreground">Experts</h2>
          <span className="text-[11px] text-faint tabular">{experts.length}</span>
        </div>
        <div className="mt-2.5 rule-strong" />
      </header>
      {experts.length === 0 ? (
        <p className="px-4 py-5 text-[13px] text-faint">
          The orchestrator hasn&apos;t routed yet.
        </p>
      ) : (
        <ul className="divide-y divide-border/60">
          {experts.map((expert) => {
            const meta = EXPERT_STATUS[expert.status];
            return (
              <li key={expert.id} className="px-4 py-3.5">
                <div className="flex items-center justify-between gap-3">
                  <p className="min-w-0 truncate font-mono text-[13px]">
                    {expert.name}
                    <span className="text-faint">/{expert.domain.toLowerCase()}</span>
                  </p>
                  <span className={cn("flex shrink-0 items-center gap-1.5 text-[12px] font-medium", meta.tone)}>
                    {meta.live && (
                      <span className="size-1.5 animate-pulse-dot rounded-full bg-current" aria-hidden />
                    )}
                    {meta.label}
                  </span>
                </div>
                {expert.summary ? (
                  <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
                    {expert.summary}
                  </p>
                ) : (
                  <p className="mt-1.5 text-[12px] text-faint tabular">
                    {expert.toolCalls} tool call{expert.toolCalls === 1 ? "" : "s"}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function SourcesPanel({ sources, className }: { sources: Source[]; className?: string }) {
  if (sources.length === 0) return null;
  return (
    <section
      aria-label="Sources"
      className={cn("rounded-lg border border-border bg-surface", className)}
    >
      <header className="px-4 pt-3.5">
        <div className="flex items-baseline justify-between">
          <h2 className="display-soft text-[15px] leading-none text-foreground">Sources</h2>
          <span className="text-[11px] text-faint tabular">{sources.length}</span>
        </div>
        <div className="mt-2.5 rule-strong" />
      </header>
      <ol className="divide-y divide-border/60">
        {sources.map((source, i) => {
          const href = normalizeHttpUrl(source.url);
          const content = (
            <>
              <span className="mt-px shrink-0 font-mono text-[11px] text-faint tabular">
                [{i + 1}]
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-foreground group-hover:text-primary">
                  {source.title}
                </span>
                <span className="block truncate text-[12px] text-faint">{source.domain}</span>
              </span>
              <ExternalLink className="mt-1 size-3.5 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
            </>
          );
          return (
            <li key={source.id}>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-muted"
                >
                  {content}
                </a>
              ) : (
                <div className="flex items-start gap-3 px-4 py-3" data-invalid-source-url>
                  {content}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
