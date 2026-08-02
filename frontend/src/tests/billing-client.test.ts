import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpClient } from "@/lib/api/http";

function okJson(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    statusText: status === 201 ? "Created" : "OK",
    json: async () => body,
  };
}

const checkout = {
  id: "chk_1",
  kind: "upgrade" as const,
  status: "pending" as const,
  planId: "pro" as const,
  creditAmount: null,
  createdAt: "2026-08-01T12:00:00+00:00",
  settledAt: null,
};

describe("HttpClient billing contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the required upgrade kind instead of the rejected legacy bare planId body", async () => {
    const fetch = vi.fn().mockResolvedValue(okJson(checkout, 201));
    vi.stubGlobal("fetch", fetch);

    await expect(
      new HttpClient().startCheckout({ kind: "upgrade", planId: "pro" }),
    ).resolves.toEqual(checkout);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/billing\/checkout$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ kind: "upgrade", planId: "pro" }),
      }),
    );
  });

  it("sends positive add-on credit checkout input without a planId", async () => {
    const addOn = { ...checkout, kind: "add_on" as const, planId: null, creditAmount: 250_000 };
    const fetch = vi.fn().mockResolvedValue(okJson(addOn, 201));
    vi.stubGlobal("fetch", fetch);

    await new HttpClient().startCheckout({ kind: "add_on", creditAmount: 250_000 });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/billing\/checkout$/),
      expect.objectContaining({
        body: JSON.stringify({ kind: "add_on", creditAmount: 250_000 }),
      }),
    );
  });

  it("polls owner checkout status and reads the mock portal without any confirmation call", async () => {
    const portal = {
      mode: "mock" as const,
      planId: "starter" as const,
      maxAddOnCredits: 20_000_000,
      checkouts: [checkout],
      subscription: { status: "active" as const, cancelEffectiveAt: null },
    };
    const fetch = vi.fn()
      .mockResolvedValueOnce(okJson(checkout))
      .mockResolvedValueOnce(okJson(portal));
    vi.stubGlobal("fetch", fetch);
    const client = new HttpClient();

    await expect(client.getCheckoutStatus("chk_1")).resolves.toEqual(checkout);
    await expect(client.openBillingPortal()).resolves.toEqual(portal);
    const requestedUrls = fetch.mock.calls.map(([requested]) => String(requested));
    expect(requestedUrls[0]).toMatch(/\/billing\/checkouts\/chk_1$/);
    expect(requestedUrls[1]).toMatch(/\/billing\/portal$/);
    expect(requestedUrls.join(" ")).not.toContain("/billing/mock/confirm");
  });

  // These three hit specification/api/requests/2026-08-02_billing-cancel-
  // downgrade-invoices.md — filed, not yet built server-side. Frontend is
  // built and live against the mock regardless (owner: the filed contract
  // is the unblock, not a reason to wait) — these tests just prove
  // HttpClient calls the exact routes/payloads that contract promises, so
  // the swap to a real backend is mechanical once it lands.
  it("calls the filed invoices route with no body", async () => {
    const fetch = vi.fn().mockResolvedValue(okJson({ invoices: [] }));
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().getInvoices();
    expect(String(fetch.mock.calls[0][0])).toMatch(/\/billing\/invoices$/);
  });

  it("posts an optional reason to the filed cancel route", async () => {
    const fetch = vi.fn().mockResolvedValue(
      okJson({ status: "cancel_scheduled", cancelEffectiveAt: "2026-09-01T00:00:00.000Z" }),
    );
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().cancelSubscription("too expensive");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/billing\/cancel$/),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "too expensive" }) }),
    );
  });

  it("posts the target plan to the filed downgrade route", async () => {
    const fetch = vi.fn().mockResolvedValue(
      okJson({ status: "applied", effectiveAt: "2026-08-03T00:00:00.000Z", newPlanId: "starter" }),
    );
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().downgradePlan("starter");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/billing\/downgrade$/),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ targetPlanId: "starter" }) }),
    );
  });
});
