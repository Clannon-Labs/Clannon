import {
  FileText,
  ShieldCheck,
  GitBranch,
  Filter,
  FileCheck2,
  type LucideIcon,
} from "lucide-react";
import { SectionHeading } from "@/components/marketing/section-heading";

interface Stage {
  icon: LucideIcon;
  name: string;
  description: string;
}

const STAGES: Stage[] = [
  {
    icon: FileText,
    name: "Brief",
    description:
      "Paste the client brief — raw notes, an email thread, a half-formed idea. That's enough.",
  },
  {
    icon: ShieldCheck,
    name: "Sanitize & verify",
    description:
      "Every input passes malware scanning, PII checks, and a semantic verifier before any reasoning touches it.",
  },
  {
    icon: GitBranch,
    name: "Parallel research",
    description:
      "The orchestrator measures how many domains your question spans and spawns one expert per domain — in parallel, with your memory already loaded.",
  },
  {
    icon: Filter,
    name: "Quality filter",
    description:
      "Citations are verified against their sources. Ungrounded claims don't survive. PII never leaves.",
  },
  {
    icon: FileCheck2,
    name: "Report",
    description:
      "A sourced, structured deliverable — and everything learned is filed into memory for next time.",
  },
];

export function PipelineSection() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-5 py-20 sm:py-28">
      <SectionHeading
        kicker="How it works"
        intro="Clannon is a pipeline, not a chatbot. Every run moves through the same auditable stages — and you watch each decision as it happens."
      >
        One brief in. Five stages. A report you can put your name on.
      </SectionHeading>

      <ol
        className="mt-12 grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 lg:grid-cols-5"
      >
        {STAGES.map((stage, i) => (
          <li key={stage.name} className="group relative h-full bg-surface p-6 transition-colors hover:bg-surface-raised">
            <div className="flex items-center justify-between">
              <stage.icon className="size-5 text-primary" aria-hidden />
              <span className="tag-label text-faint">0{i + 1}</span>
            </div>
            <h3 className="display-soft mt-5 text-[1.15rem] leading-none">{stage.name}</h3>
            <p className="mt-2.5 text-sm leading-relaxed text-muted-foreground">
              {stage.description}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
