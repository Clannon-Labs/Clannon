import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpClient } from "@/lib/api/http";
import { parseRunEvent } from "@/lib/api/run-event";
import type { RunEvent } from "@/lib/api/types";

const validSource = {
  id: "safe",
  title: "Safe source",
  url: "https://example.com/report",
  domain: "example.com",
};

describe("RunEvent runtime validation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps valid HTTP(S) sources and drops dangerous sources within one frame", () => {
    expect(
      parseRunEvent({
        type: "sources",
        sources: [
          validSource,
          { ...validSource, id: "unsafe", url: "javascript:alert(document.domain)" },
          { ...validSource, id: "http", url: "http://localhost:8000/source" },
        ],
      }),
    ).toEqual({
      type: "sources",
      sources: [validSource, { ...validSource, id: "http", url: "http://localhost:8000/source" }],
    });
  });

  it.each([
    { type: "status", status: "unknown" },
    { type: "usage", tokensUsed: "many" },
    { type: "message_delta", text: 12 },
    { type: "new_future_event", value: true },
    null,
  ])("rejects malformed event %#", (event) => {
    expect(parseRunEvent(event)).toBeNull();
  });

  it("skips malformed frames without killing later stream events", async () => {
    const frames = [
      JSON.stringify({ type: "status", status: "queued" }),
      "not-json",
      JSON.stringify({ type: "status", status: "unknown" }),
      JSON.stringify({
        type: "sources",
        sources: [validSource, { ...validSource, id: "unsafe", url: "data:text/html,bad" }],
      }),
      JSON.stringify({ type: "report_done" }),
      "[DONE]",
    ]
      .map((payload) => `data: ${payload}\n\n`)
      .join("");
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frames));
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, statusText: "OK", body }),
    );

    const events: RunEvent[] = [];
    for await (const event of new HttpClient().streamRun(
      "run_1",
      new AbortController().signal,
    )) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "status", status: "queued" },
      { type: "sources", sources: [validSource] },
      { type: "report_done" },
    ]);
  });
});
