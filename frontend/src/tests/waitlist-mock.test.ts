import { afterEach, describe, expect, it } from "vitest";
import { MockClient } from "@/lib/api/mock";
import { ApiError } from "@/lib/api";

afterEach(() => window.localStorage.clear());

describe("mock waitlist gate", () => {
  it("getRemoteConfig reports the gate on, mirroring the committed backend default", async () => {
    const client = new MockClient();
    const config = await client.getRemoteConfig();
    expect(config.waitlistEnabled).toBe(true);
  });

  it("rejects open signup (no approvalToken) with the real backend's 403 message", async () => {
    const client = new MockClient();
    await expect(
      client.signup({ name: "New", email: "new@example.com", password: "correct-horse" }),
    ).rejects.toMatchObject({
      status: 403,
      message: "Signups are invite-only right now. Join the waitlist.",
    });
  });

  it("rejects an approvalToken that isn't the mock's known-good one, with a distinct message", async () => {
    const client = new MockClient();
    await expect(
      client.signup({ name: "New", password: "correct-horse", approvalToken: "wrong-token" }),
    ).rejects.toMatchObject({
      status: 403,
      message: "This invite link is invalid or has expired.",
    });
  });

  it("accepts the mock's known-good approval token and ignores any email in the body", async () => {
    const client = new MockClient();
    const user = await client.signup({
      name: "New Operator",
      email: "ignored@example.com",
      password: "correct-horse",
      approvalToken: "demo-approved",
    });
    // the account's email comes from the token, never the body — mirrors
    // backend/api/app.py: "ignores `email` (the token supplies it)"
    expect(user.email).not.toBe("ignored@example.com");
    expect(user.plan).toBe("free");
  });

  it("still enforces the password-length rule ahead of the gate check", async () => {
    const client = new MockClient();
    await expect(
      client.signup({ name: "New", password: "short", approvalToken: "demo-approved" }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("mock waitlist join/resend — non-disclosure", () => {
  it("join always resolves, whatever the address", async () => {
    const client = new MockClient();
    await expect(
      client.joinWaitlist({ email: "anyone@example.com" }),
    ).resolves.toBeUndefined();
  });

  it("join accepts an optional note", async () => {
    const client = new MockClient();
    await expect(
      client.joinWaitlist({ email: "anyone@example.com", note: "excited to try this" }),
    ).resolves.toBeUndefined();
  });

  it("resend always resolves too — same non-oracle shape as join", async () => {
    const client = new MockClient();
    await expect(
      client.resendWaitlistVerification("anyone@example.com"),
    ).resolves.toBeUndefined();
  });

  it("rate-limits rapid repeated calls the same way regardless of address (shared limiter, not per-email)", async () => {
    const client = new MockClient();
    for (let i = 0; i < 5; i++) {
      await client.joinWaitlist({ email: `person-${i}@example.com` });
    }
    await expect(
      client.joinWaitlist({ email: "one-more@example.com" }),
    ).rejects.toMatchObject({ status: 429 });
  });
});
