import { describe, it, expect, vi, afterEach } from "vitest";
import { HttpClient } from "@/lib/api/http";
import { ApiError } from "@/lib/api/types";

/**
 * FastAPI wraps whatever an endpoint raises inside {"detail": ...}. Most
 * endpoints raise a plain string; billing.admit_run raises a STRUCTURED
 * dict ({code, message, used, budget, ...}) so the 402 carries a
 * machine-readable reason, not just prose. The parser has to unwrap both
 * shapes — this pins the structured-dict case, which errorMessage() used to
 * silently drop (falling back to a generic status-text message instead of
 * the real "Token budget exhausted..." reason the backend sent).
 */
describe("HttpClient error parsing — structured HTTPException detail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("surfaces the real message from a structured 402 detail, not a generic fallback", async () => {
    const body = {
      detail: {
        code: "token_budget_exhausted",
        message: "Token budget exhausted for this billing period.",
        used: 312_000,
        budget: 100_000,
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 402,
        statusText: "Payment Required",
        json: async () => body,
      }),
    );

    const client = new HttpClient();
    await expect(client.createRun("Some brief")).rejects.toMatchObject({
      message: "Token budget exhausted for this billing period.",
      status: 402,
    });
  });

  it("still handles a plain string detail (the common case)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: async () => ({ detail: "Say a little more to get started." }),
      }),
    );

    const client = new HttpClient();
    let error: unknown;
    try {
      await client.createRun("hi");
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Say a little more to get started.");
  });
});
