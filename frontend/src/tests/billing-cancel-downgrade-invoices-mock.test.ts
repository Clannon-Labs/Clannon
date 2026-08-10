import { afterEach, describe, expect, it } from "vitest";
import { MockClient } from "@/lib/api/mock";
import { ApiError } from "@/lib/api";

afterEach(() => window.localStorage.clear());

async function proAccount(): Promise<MockClient> {
  const client = new MockClient();
  await client.login({ email: "demo@example.com", password: "correct-horse" });
  return client;
}

describe("mock cancel subscription", () => {
  it("schedules a reversion to Free at the current period's end, not immediately", async () => {
    const client = await proAccount();
    const before = await client.openBillingPortal();
    expect(before.subscription).toEqual({ status: "active", cancelEffectiveAt: null });

    const result = await client.cancelSubscription("too expensive");
    expect(result.status).toBe("cancel_scheduled");
    expect(result.cancelEffectiveAt).not.toBeNull();

    // access is NOT revoked immediately — plan stays on the account
    const user = await client.me();
    expect(user?.plan).toBe("pro");

    const after = await client.openBillingPortal();
    expect(after.subscription).toEqual(result);
  });

  it("rejects a second cancel while one is already scheduled", async () => {
    const client = await proAccount();
    await client.cancelSubscription();
    await expect(client.cancelSubscription()).rejects.toThrow(ApiError);
  });

  it("undo clears the schedule", async () => {
    const client = await proAccount();
    await client.cancelSubscription();
    await client.undoCancelSubscription();
    const portal = await client.openBillingPortal();
    expect(portal.subscription).toEqual({ status: "active", cancelEffectiveAt: null });
  });

  it("a fresh signup never inherits a stale cancellation flag from browser storage", async () => {
    const first = await proAccount();
    await first.cancelSubscription();

    // simulate a full page reload: a brand-new MockClient instance reads
    // whatever's still in localStorage — this is exactly the bug class
    // that shipped once already for EMPTY_ACCOUNT_KEY (see mock.ts comments)
    const second = new MockClient();
    await second.signup({ name: "New", password: "correct-horse", approvalToken: "demo-approved" });
    const portal = await second.openBillingPortal();
    expect(portal.subscription).toEqual({ status: "active", cancelEffectiveAt: null });
  });
});

describe("mock downgrade", () => {
  it("applies immediately when usage fits the target plan's budget", async () => {
    const client = await proAccount();
    const result = await client.downgradePlan("starter");
    expect(result).toMatchObject({ status: "applied", newPlanId: "starter" });
    const user = await client.me();
    expect(user?.plan).toBe("starter");
  });

  it("blocks with an explaining 409 when this period's usage exceeds the target budget", async () => {
    const client = await proAccount();
    // seeded demo runs put real usage on the account; free's 100k budget is
    // far below it — a genuine over-budget target, not a contrived one
    await expect(client.downgradePlan("free")).rejects.toMatchObject({
      status: 409,
      code: "usage_exceeds_target_budget",
    });
    // blocked means blocked — plan must not have changed
    const user = await client.me();
    expect(user?.plan).toBe("pro");
  });

  it("rejects a target that isn't actually a downgrade", async () => {
    const client = await proAccount();
    await expect(client.downgradePlan("agency")).rejects.toMatchObject({ status: 422 });
  });
});

describe("mock invoices", () => {
  it("is empty on a fresh signup — never a fabricated invoice", async () => {
    const client = new MockClient();
    await client.signup({ name: "New", password: "correct-horse", approvalToken: "demo-approved" });
    const { invoices } = await client.getInvoices();
    expect(invoices).toEqual([]);
  });

  it("includes the current paid plan's period charge for a returning account", async () => {
    const client = await proAccount();
    const { invoices } = await client.getInvoices();
    expect(invoices.some((i) => i.description.startsWith("Pro plan"))).toBe(true);
  });

  it("adds a real invoice row once a checkout actually settles, not on every checkout", async () => {
    const client = await proAccount();
    const before = await client.getInvoices();

    const checkout = await client.startCheckout({ kind: "add_on", creditAmount: 100_000 });
    expect(checkout.status).toBe("pending");
    // a pending checkout is NOT yet an invoice — the mock has no browser-side
    // settlement path (confirmation is server/webhook-only), so this proves
    // the invoice list isn't naively mirroring the checkout list 1:1
    const stillPending = await client.getInvoices();
    expect(stillPending.invoices.length).toBe(before.invoices.length);
  });
});
