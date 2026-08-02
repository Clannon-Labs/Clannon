import { afterEach, describe, expect, it } from "vitest";
import { MockClient } from "@/lib/api/mock";

afterEach(() => window.localStorage.clear());

describe("mock usage latency", () => {
  it("is genuinely empty on a fresh signup — never a fabricated estimate", async () => {
    const client = new MockClient();
    await client.signup({ name: "New Operator", email: "new@example.com", password: "correct-horse" });
    const usage = await client.getUsage();

    expect(usage.latency).toBeDefined();
    expect(usage.latency?.timeToFirstMessageMs).toEqual({
      sampleSize: 0,
      excluded: 0,
      p50: null,
      p95: null,
    });
    expect(usage.latency?.totalDurationMs).toEqual({
      sampleSize: 0,
      excluded: 0,
      p50: null,
      p95: null,
    });
  });

  it("has a plausible seeded estimate on a returning demo account", async () => {
    const client = new MockClient();
    await client.login({ email: "demo@example.com", password: "correct-horse" });
    const usage = await client.getUsage();

    expect(usage.latency?.totalDurationMs.sampleSize).toBeGreaterThan(0);
    expect(usage.latency?.totalDurationMs.p50).not.toBeNull();
    // sane bounds — a demo estimate that reads as "instant" or "hours" would
    // be worse than no estimate at all
    expect(usage.latency!.totalDurationMs.p50!).toBeGreaterThan(5_000);
    expect(usage.latency!.totalDurationMs.p50!).toBeLessThan(5 * 60_000);
  });

  it("records a real elapsed-time sample as a run actually completes", async () => {
    const client = new MockClient();
    await client.login({ email: "demo@example.com", password: "correct-horse" });
    const before = (await client.getUsage()).latency!.totalDurationMs.sampleSize;

    const { id } = await client.createRun("A brief long enough to pass validation.");
    const controller = new AbortController();
    const iterator = client.streamRun(id, controller.signal)[Symbol.asyncIterator]();
    // let the stream begin, then stop it — reaches the cancelled terminal
    // path (recordTotal() on every terminal branch, not just full delivery)
    // without waiting out the full ~35s script
    await iterator.next();
    await client.cancelRun(id);
    // drain until the generator naturally ends (cancellation settles on its
    // next scripted tick, not synchronously)
    let done = false;
    while (!done) {
      const step = await iterator.next();
      done = Boolean(step.done);
    }

    const after = (await client.getUsage()).latency!.totalDurationMs.sampleSize;
    expect(after).toBe(before + 1);
  }, 10_000);
});
