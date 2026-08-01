import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// SessionModelPicker (rendered inside Composer) calls useModelConfig — give
// it an empty roster so the picker renders without needing react-query.
vi.mock("@/lib/api/hooks", () => ({
  useModelConfig: () => ({ data: [] }),
}));

import { Composer } from "@/components/app/composer";
import { ApiError } from "@/lib/api";

function noop() {}

describe("Composer — budgetExhausted", () => {
  it("keeps Send enabled and shows no exhausted copy when the account has budget", () => {
    render(
      <Composer value="A long enough brief to pass validation" onChange={noop} onSubmit={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(screen.queryByText(/billing period is out of tokens/i)).not.toBeInTheDocument();
  });

  it("disables Send and explains why once the budget is exhausted, without blocking typing", () => {
    const onChange = vi.fn();
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={onChange}
        onSubmit={vi.fn()}
        budgetExhausted
      />,
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByText(/billing period is out of tokens/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review billing options" })).toHaveAttribute(
      "href",
      "/app/settings?tab=billing",
    );
    // typing itself is never blocked — only sending is
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "still typing" },
    });
    expect(onChange).toHaveBeenCalledWith("still typing");
  });

  // Enter-to-send is gated on isFinePointer() (matchMedia "(pointer: fine)"),
  // which the global test setup stubs to always report `false` — so without
  // forcing it `true` here, this test would pass even with the budgetExhausted
  // check deleted, for the wrong reason. Two tests, same stub: one proves
  // Enter really can submit at all in this harness, the other proves
  // budgetExhausted is what stops it — not an unrelated always-false mock.
  function withFinePointer(matches: boolean, run: () => void) {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    try {
      run();
    } finally {
      window.matchMedia = original;
    }
  }

  it("Enter submits when nothing is blocking it (sanity check for the test below)", () => {
    withFinePointer(true, () => {
      const onSubmit = vi.fn();
      render(
        <Composer value="A long enough brief to pass validation" onChange={noop} onSubmit={onSubmit} />,
      );
      fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Enter" });
      expect(onSubmit).toHaveBeenCalledOnce();
    });
  });

  it("does not submit on Enter while budget-exhausted", () => {
    withFinePointer(true, () => {
      const onSubmit = vi.fn();
      render(
        <Composer
          value="A long enough brief to pass validation"
          onChange={noop}
          onSubmit={onSubmit}
          budgetExhausted
        />,
      );
      fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), { key: "Enter" });
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it("turns a stale structured 402 into reset-date, add-on, and upgrade actions", () => {
    const error = new ApiError(
      "Token budget exhausted for this billing period.",
      402,
      "token_budget_exhausted",
      120_000,
      100_000,
      "2026-08-31",
      [
        { kind: "add_on", endpoint: "/billing/checkout" },
        { kind: "upgrade", endpoint: "/billing/checkout" },
      ],
      true,
    );
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        submitError={error}
      />,
    );

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByText(/120k used of 100k/)).toBeInTheDocument();
    expect(screen.getByText(/reset on August 31, 2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add token credits" })).toHaveAttribute(
      "href",
      "/app/settings?tab=billing&action=add_on",
    );
    expect(screen.getByRole("link", { name: "See upgrade plans" })).toHaveAttribute(
      "href",
      "/app/settings?tab=billing&action=upgrade",
    );
  });
});
