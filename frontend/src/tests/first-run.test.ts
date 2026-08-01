import { afterEach, describe, expect, it } from "vitest";
import { MockClient } from "@/lib/api/mock";
import { planById } from "@/config/plans";
import {
  readTextDraft,
  runReplyDraftKey,
  workspaceDraftKey,
  writeTextDraft,
} from "@/lib/browser-drafts";

afterEach(() => window.localStorage.clear());

describe("mock signup first-user state", () => {
  it("does not expose seeded projects, runs, memory, or usage", async () => {
    const client = new MockClient();

    const user = await client.signup({
      name: "New Operator",
      email: "new@example.com",
      password: "correct-horse",
    });
    const [projects, runs, memory, usage] = await Promise.all([
      client.listProjects(),
      client.listRuns(),
      client.listMemory(),
      client.getUsage(),
    ]);

    expect(user.plan).toBe("free");
    expect(projects).toEqual([]);
    expect(runs).toEqual([]);
    expect(memory).toEqual([]);
    expect(usage.used).toBe(0);
    expect(usage.periodEndExclusive).toBe(true);
    expect(usage.baseBudget).toBe(planById("free").tokenBudget);
    expect(usage.additionalCredits).toBe(0);
    expect(usage.budget).toBe(planById("free").tokenBudget);
    expect(usage.cacheReadTokens).toBe(0);
    expect(usage.cacheWriteTokens).toBe(0);
    expect(usage.byDay.every((day) => day.tokens === 0)).toBe(true);
  });

  it("creates a pending mock upgrade without applying entitlement in the browser", async () => {
    const client = new MockClient();
    await client.signup({
      name: "New Operator",
      email: "new@example.com",
      password: "correct-horse",
    });

    const checkout = await client.startCheckout({ kind: "upgrade", planId: "starter" });
    expect(checkout).toMatchObject({
      kind: "upgrade",
      status: "pending",
      planId: "starter",
      creditAmount: null,
      settledAt: null,
    });
    await expect(client.getCheckoutStatus(checkout.id)).resolves.toEqual(checkout);
    await expect(client.openBillingPortal()).resolves.toMatchObject({
      mode: "mock",
      planId: "free",
      checkouts: [checkout],
    });
    await expect(client.me()).resolves.toMatchObject({ plan: "free" });
  });
});

describe("workspace draft recovery", () => {
  function memoryStorage() {
    const values = new Map<string, string>();
    return {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };
  }

  it("scopes drafts by user and project, then restores exact text", () => {
    const storage = memoryStorage();
    const key = workspaceDraftKey("user_1", "project_1");
    writeTextDraft(storage, key, "A sensitive, unfinished brief.");

    expect(readTextDraft(storage, key)).toBe("A sensitive, unfinished brief.");
    expect(workspaceDraftKey("user_2", "project_1")).not.toBe(key);
    expect(workspaceDraftKey("user_1", "project_2")).not.toBe(key);
  });

  it("drops expired or malformed drafts instead of breaking onboarding", () => {
    const storage = memoryStorage();
    const key = workspaceDraftKey("user_1");
    storage.setItem(key, JSON.stringify({ value: "old", updatedAt: 1 }));

    expect(readTextDraft(storage, key, 24 * 60 * 60 * 1000 + 2)).toBe("");
    storage.setItem(key, "{broken");
    expect(readTextDraft(storage, key)).toBe("");
  });

  it("restores a user-scoped reply without claiming it was queued", () => {
    const storage = memoryStorage();
    const key = runReplyDraftKey("user_1", "run_1");
    writeTextDraft(storage, key, "Narrow this to agencies under 20 people.");

    expect(readTextDraft(storage, key)).toBe("Narrow this to agencies under 20 people.");
    expect(runReplyDraftKey("user_2", "run_1")).not.toBe(key);
  });
});
