import { z } from "zod";
import { normalizeHttpUrl } from "@/config/url-policy";
import type { RunEvent, Source } from "./types";

const decisionLogEntrySchema = z.object({
  id: z.string(),
  ts: z.string(),
  kind: z.enum([
    "hydration",
    "route",
    "expert_spawn",
    "tool_call",
    "observation",
    "answer",
    "warning",
    "error",
  ]),
  title: z.string(),
  detail: z.string().optional(),
  meta: z.record(z.string(), z.string()).optional(),
});

const expertStateSchema = z.object({
  id: z.string(),
  name: z.string(),
  domain: z.string(),
  status: z.enum(["spawned", "working", "summarizing", "done", "failed"]),
  summary: z.string().optional(),
  toolCalls: z.number().nonnegative(),
});

const sourceSchema = z
  .object({
    id: z.string(),
    title: z.string(),
    url: z.string(),
    domain: z.string(),
  })
  .transform((source, context): Source => {
    const url = normalizeHttpUrl(source.url);
    if (!url) {
      context.addIssue({
        code: "custom",
        path: ["url"],
        message: "Source URL must use http:// or https://.",
      });
      return z.NEVER;
    }
    return { ...source, url };
  });

const sourcesEnvelopeSchema = z.object({
  type: z.literal("sources"),
  sources: z.array(z.unknown()),
});

const nonSourceRunEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("status"),
    status: z.enum([
      "queued",
      "sanitizing",
      "verifying",
      "orchestrating",
      "filtering",
      "delivered",
      "blocked",
      "failed",
      "cancelled",
    ]),
  }),
  z.object({ type: z.literal("log"), entry: decisionLogEntrySchema }),
  z.object({ type: z.literal("expert"), expert: expertStateSchema }),
  z.object({ type: z.literal("message_delta"), text: z.string() }),
  z.object({ type: z.literal("message_done") }),
  z.object({ type: z.literal("report_delta"), text: z.string() }),
  z.object({ type: z.literal("report_done") }),
  z.object({ type: z.literal("usage"), tokensUsed: z.number().nonnegative() }),
  z.object({
    type: z.literal("verification"),
    state: z.enum(["grounded", "partial", "ungrounded", "not_applicable"]),
  }),
]);

/**
 * Validate an untrusted SSE payload before it joins rendered run state.
 * Invalid frames are skipped by the stream reader. A sources frame keeps its
 * valid citations while dropping only entries whose shape or URL is unsafe.
 */
export function parseRunEvent(input: unknown): RunEvent | null {
  const sourcesEnvelope = sourcesEnvelopeSchema.safeParse(input);
  if (sourcesEnvelope.success) {
    const sources = sourcesEnvelope.data.sources.flatMap((candidate) => {
      const parsed = sourceSchema.safeParse(candidate);
      return parsed.success ? [parsed.data] : [];
    });
    return { type: "sources", sources };
  }

  const event = nonSourceRunEventSchema.safeParse(input);
  return event.success ? event.data : null;
}
