import { Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CompletionReason } from "@/lib/api";

/** Why the loop stopped short of finishing — distinct from `verificationState`
 *  (whether the claims it DID make are grounded) and `status` (how it ended).
 *  A partial run is routinely delivered and grounded at once. */
function completionMessage(reason: CompletionReason): { title: string; body: string } {
  switch (reason) {
    case "timeout":
      return {
        title: "Ran out of time before finishing",
        body: "It hit the per-run time budget before covering everything the brief asked for. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    case "rate_limit":
      return {
        title: "Interrupted by a rate limit",
        body: "An upstream rate limit stopped it before it finished everything planned. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    case "error":
      return {
        title: "Interrupted by an error",
        body: "Something failed mid-run before it finished everything planned. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
    default:
      return {
        title: "Didn't finish everything planned",
        body: "The loop stopped before covering the full brief. What's below is real and grounded in what it gathered — ask it to continue and it'll pick up where it stopped.",
      };
  }
}

/** The small pill next to the terminal status badge — a quick scan signal
 *  that this delivery didn't cover everything, without reading the report. */
export function CompletionBadge() {
  return (
    <span className="tag-label inline-flex items-center gap-1.5 rounded-full bg-memory-soft px-2.5 py-1 text-memory">
      <Clock className="size-3.5" aria-hidden />
      Partial
    </span>
  );
}

/** Incomplete but real — not an error, not a re-run of what already shipped.
 *  Reads its cause instead of forcing you into the report to guess why it
 *  feels short, and offers one concrete way forward. */
export function CompletionBanner({
  reason,
  onContinue,
}: {
  reason: CompletionReason;
  onContinue: () => void;
}) {
  const { title, body } = completionMessage(reason);
  return (
    <div role="status" className="mt-5 border-l-2 border-warning/40 pl-4">
      <p className="tag-label flex items-center gap-1.5 text-memory">
        <Clock className="size-3.5" aria-hidden />
        {title}
      </p>
      <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">{body}</p>
      <Button variant="outline" size="sm" className="mt-3" onClick={onContinue}>
        Continue this run
      </Button>
    </div>
  );
}
