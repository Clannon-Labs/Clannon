"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, FileCheck2, ShieldCheck, Square } from "lucide-react";
import { useCreateProject } from "@/lib/api/hooks";
import { useSelectProject } from "@/components/app/project-provider";
import type { Project } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const DELIVERABLES = [
  {
    id: "recommendation",
    label: "Decision memo",
    requirement: "a clear recommendation, risks, alternatives, and next actions",
  },
  {
    id: "comparison",
    label: "Comparison",
    requirement: "a comparison table, meaningful differences, tradeoffs, and a recommendation",
  },
  {
    id: "research",
    label: "Research brief",
    requirement: "an executive summary, key findings, evidence, risks, and open questions",
  },
] as const;

export function buildFirstBrief({
  project,
  decision,
  context,
  deliverable,
}: {
  project: string;
  decision: string;
  context: string;
  deliverable: (typeof DELIVERABLES)[number]["id"];
}): string {
  const chosen = DELIVERABLES.find((item) => item.id === deliverable) ?? DELIVERABLES[0];
  const sentence = (label: string, value: string) => {
    const trimmed = value.trim();
    return `${label}: ${trimmed}${/[.!?]$/.test(trimmed) ? "" : "."}`;
  };
  return [
    `For ${project}, prepare a ${chosen.label.toLowerCase()}.`,
    sentence("Decision or outcome", decision),
    context.trim() ? sentence("Context and constraints", context) : "",
    `Deliverable requirements: ${chosen.requirement}. Cite every material claim and separate facts from assumptions.`,
  ]
    .filter(Boolean)
    .join(" ");
}

/**
 * First-run path for a genuinely empty account. It asks only for information
 * needed to produce useful work, then converts it into an editable brief.
 * No architecture vocabulary, mandatory tour, or irreversible wizard state.
 */
export function FirstRunGuide({
  currentProject,
  onUseBrief,
  onUseExample,
}: {
  currentProject?: Project;
  onUseBrief: (brief: string, projectId?: string) => void;
  onUseExample: () => void;
}) {
  const createProject = useCreateProject();
  const selectProject = useSelectProject();
  const [project, setProject] = useState("");
  const [decision, setDecision] = useState("");
  const [context, setContext] = useState("");
  const [deliverable, setDeliverable] =
    useState<(typeof DELIVERABLES)[number]["id"]>("recommendation");
  const [error, setError] = useState<string | null>(null);

  const projectName = currentProject?.name ?? project.trim();
  const ready = projectName.length >= 2 && decision.trim().length >= 10;

  function finish(name: string, projectId: string) {
    onUseBrief(
      buildFirstBrief({
        project: name,
        decision,
        context,
        deliverable,
      }),
      projectId,
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setError(null);
    if (currentProject) {
      finish(currentProject.name, currentProject.id);
      return;
    }
    createProject.mutate(
      { name: projectName, seedFacts: context.trim() || undefined },
      {
        onSuccess: (created) => {
          selectProject(created.id);
          finish(created.name, created.id);
        },
        onError: () => setError("Could not create the project. Your answers are still here."),
      },
    );
  }

  return (
    <section
      aria-labelledby="first-run-title"
      className="mt-8 overflow-hidden rounded-2xl border border-border-strong bg-surface sm:mt-10"
    >
      <div className="border-b border-border bg-surface-raised px-5 py-4 sm:px-6">
        <p className="tag-label text-primary">First assignment</p>
        <h2 id="first-run-title" className="display-soft mt-2 text-[1.55rem] leading-tight">
          Start with decision, not prompt craft.
        </h2>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
          Give Clannon enough context to shape a useful brief. You can edit every word before
          anything runs.
        </p>
      </div>

      <form onSubmit={submit} className="grid gap-5 p-5 sm:p-6">
        {!currentProject && (
          <Input
            label="Client or project"
            value={project}
            onChange={(event) => setProject(event.target.value)}
            placeholder="Acme · Q4 expansion"
            autoComplete="organization"
            required
          />
        )}

        <Textarea
          label="What decision or outcome do you need?"
          value={decision}
          onChange={(event) => setDecision(event.target.value)}
          placeholder="Should we enter the UK this year, and what would make it viable?"
          rows={3}
          required
        />

        <Textarea
          label="Useful context or constraints (optional)"
          value={context}
          onChange={(event) => setContext(event.target.value)}
          placeholder="Current position, audience, budget, deadline, known facts, or material to avoid."
          rows={3}
        />

        <fieldset>
          <legend className="text-[13px] font-medium text-foreground">What should come back?</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {DELIVERABLES.map((item) => {
              const selected = deliverable === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setDeliverable(item.id)}
                  className={cn(
                    "min-h-11 rounded-lg border px-3 py-2.5 text-left text-[13px] transition-colors",
                    selected
                      ? "border-primary bg-primary-soft font-medium text-primary"
                      : "border-border bg-background text-muted-foreground hover:border-border-strong hover:text-foreground",
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="grid gap-2 rounded-lg border border-border bg-background px-4 py-3 text-[12px] text-muted-foreground sm:grid-cols-3">
          <span className="flex items-center gap-2">
            <FileCheck2 className="size-3.5 text-primary" aria-hidden />
            Sourced deliverable
          </span>
          <span className="flex items-center gap-2">
            <ShieldCheck className="size-3.5 text-primary" aria-hidden />
            Claims checked
          </span>
          <span className="flex items-center gap-2">
            <Square className="size-3 text-faint" aria-hidden />
            Stop anytime
          </span>
        </div>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={onUseExample}
            className="min-h-10 text-left text-[13px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Use a complete example instead
          </button>
          <Button type="submit" disabled={!ready} loading={createProject.isPending}>
            Build editable brief
            {!createProject.isPending && <ArrowRight className="size-4" aria-hidden />}
          </Button>
        </div>
      </form>
    </section>
  );
}
