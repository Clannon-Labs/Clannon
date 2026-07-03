import { Plus } from "lucide-react";
import { SectionHeading } from "@/components/marketing/section-heading";

const FAQS = [
  {
    q: "How is this different from asking ChatGPT to do research?",
    a: "Three ways. First, parallelism: Clannon measures how many domains your question spans and runs one specialist per domain simultaneously, instead of one long meandering chat. Second, the quality gate: every claim in the final report passes a citation-integrity and groundedness filter before you see it. Third — and this is the moat — memory. Your tenth run with a client knows everything the first nine learned.",
  },
  {
    q: "What exactly do I watch in the decision log?",
    a: "Every routing decision the orchestrator makes, live: which memory was loaded, why it spawned the experts it did, every search and fetch, conflicts it found between sources, and when the draft enters the quality filter. No black box — you can audit any run after the fact.",
  },
  {
    q: "What happens to my client data?",
    a: "Every input is scanned, stripped of secrets and PII flags, and verified before any model reasons over it. Memory is scoped to your account at the database layer, and the final output filter checks that no personal data leaks into deliverables. Your wiki exports as plain markdown — your knowledge stays yours.",
  },
  {
    q: "What's a token budget in practice?",
    a: "A deep multi-expert research run uses roughly 250–400k tokens. So Starter (2M) is about 5–8 deep runs a month, Pro (6M) about 15–24, plus unlimited lighter tasks. You see live usage per run and per month — no surprise overages; the pipeline stops cleanly at your budget.",
  },
  {
    q: "Can I choose which models it uses?",
    a: "Yes. Each pipeline layer: orchestrator, experts — is independently configurable, filtered to models with the capabilities that layer needs. Or leave the defaults; they're tuned for the quality/cost balance of each stage.",
  },
];

export function FaqSection() {
  return (
    <section className="hairline-t bg-surface">
      <div className="mx-auto max-w-3xl px-5 py-20 sm:py-28">
        <SectionHeading kicker="Questions">
          The things people actually ask.
        </SectionHeading>

        {/* a ruled index, not a stack of boxes — questions set in the display voice */}
        <div className="hairline-t mt-10">
          {FAQS.map((faq) => (
            <details key={faq.q} className="group hairline-b">
              <summary className="flex cursor-pointer list-none items-start justify-between gap-6 py-5 [&::-webkit-details-marker]:hidden">
                <h3 className="display-soft text-[1.15rem] leading-snug">{faq.q}</h3>
                <Plus
                  className="mt-1 size-4 shrink-0 text-faint transition-transform duration-200 group-open:rotate-45"
                  aria-hidden
                />
              </summary>
              <p className="max-w-2xl pb-6 text-sm leading-relaxed text-muted-foreground">
                {faq.a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
