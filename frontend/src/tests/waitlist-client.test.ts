import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpClient } from "@/lib/api/http";

function okJson(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    statusText: "OK",
    json: async () => body,
  };
}

// This is the already-shipped backend contract — specification/api/ROUTES.md
// §Waitlist, verified 2026-08-09 by enumerating the live FastAPI app — not a
// filed-but-unbuilt one like billing-client.test.ts's three. These prove
// HttpClient calls the real routes/payloads/shapes.
describe("HttpClient waitlist contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts email and optional note to /waitlist and discards the always-202 body", async () => {
    const fetch = vi.fn().mockResolvedValue(okJson({ status: "ok" }, 202));
    vi.stubGlobal("fetch", fetch);
    await expect(
      new HttpClient().joinWaitlist({ email: "you@studio.com", note: "referred by a friend" }),
    ).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/waitlist$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "you@studio.com", note: "referred by a friend" }),
      }),
    );
  });

  it("omits note when not given, rather than sending an empty string", async () => {
    const fetch = vi.fn().mockResolvedValue(okJson({ status: "ok" }, 202));
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().joinWaitlist({ email: "you@studio.com" });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/waitlist$/),
      expect.objectContaining({ body: JSON.stringify({ email: "you@studio.com" }) }),
    );
  });

  it("posts only email to /waitlist/resend", async () => {
    const fetch = vi.fn().mockResolvedValue(okJson({ status: "ok" }, 202));
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().resendWaitlistVerification("you@studio.com");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/waitlist\/resend$/),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "you@studio.com" }) }),
    );
  });

  it("posts approvalToken (not email) to /auth/signup once approved", async () => {
    const fetch = vi.fn().mockResolvedValue(
      okJson({ id: "u_1", name: "New", email: "you@studio.com", plan: "free" }),
    );
    vi.stubGlobal("fetch", fetch);
    await new HttpClient().signup({
      name: "New",
      password: "correct-horse",
      approvalToken: "tok_abc",
    });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/auth\/signup$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "New", password: "correct-horse", approvalToken: "tok_abc" }),
      }),
    );
  });

  it("surfaces the real 403 body when the backend rejects an unapproved signup", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: async () => ({ detail: "Signups are invite-only right now. Join the waitlist." }),
    });
    vi.stubGlobal("fetch", fetch);
    await expect(
      new HttpClient().signup({ name: "New", password: "correct-horse" }),
    ).rejects.toMatchObject({
      status: 403,
      message: "Signups are invite-only right now. Join the waitlist.",
    });
  });
});
