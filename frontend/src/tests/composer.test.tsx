import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// SessionModelPicker (rendered inside Composer) calls useModelConfig — give
// it a single unlocked role so the "customize" picker (and its selected-model
// text) has something real to render.
const ORCHESTRATOR_LAYER = {
  layer: "orchestrator",
  label: "Orchestrator",
  model: "claude-opus-5",
  default: "claude-opus-5",
  options: ["claude-opus-5", "gpt-5.5"],
  locked: false,
};
vi.mock("@/lib/api/hooks", () => ({
  useModelConfig: () => ({ data: [ORCHESTRATOR_LAYER] }),
}));

import { Composer } from "@/components/app/composer";
import { ApiError } from "@/lib/api";
import type { UsageSummary } from "@/lib/api/types";

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

function usageWithDuration(totalMs: number): UsageSummary {
  return {
    periodStart: "2026-08-01",
    periodEnd: "2026-08-31",
    periodEndExclusive: true,
    baseBudget: 1_000_000,
    additionalCredits: 0,
    budget: 1_000_000,
    used: 10_000,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    byDay: [],
    latency: {
      inPeriod: 2,
      timeToFirstMessageMs: { sampleSize: 2, excluded: 0, p50: 2000, p95: 2500 },
      totalDurationMs: { sampleSize: 2, excluded: 0, p50: totalMs, p95: totalMs + 5000 },
    },
  };
}

describe("Composer — duration estimate", () => {
  it("shows the estimate once there's a brief and account history to source it from", () => {
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        budgetUsage={usageWithDuration(4 * 60_000)}
      />,
    );
    expect(screen.getByText(/Runs like this usually take about 4 minutes\./)).toBeInTheDocument();
  });

  it("says nothing when there's no latency history yet — never a fabricated number", () => {
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Runs like this usually take/)).not.toBeInTheDocument();
  });

  it("stays quiet on an empty composer even with history available — not ambient chrome", () => {
    render(
      <Composer value="" onChange={noop} onSubmit={vi.fn()} budgetUsage={usageWithDuration(4 * 60_000)} />,
    );
    expect(screen.queryByText(/Runs like this usually take/)).not.toBeInTheDocument();
  });

  it("yields to the error message when both could show", () => {
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        budgetUsage={usageWithDuration(4 * 60_000)}
        submitError="Something went wrong"
      />,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.queryByText(/Runs like this usually take/)).not.toBeInTheDocument();
  });

  it("hides while a run is busy — the moment for this is before Send, not during", () => {
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        budgetUsage={usageWithDuration(4 * 60_000)}
        busy
      />,
    );
    expect(screen.queryByText(/Runs like this usually take/)).not.toBeInTheDocument();
  });
});

describe("Composer — templates", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("hides the save trigger when the caller doesn't pass onSaveTemplate", () => {
    render(<Composer value="A long enough brief to pass validation" onChange={noop} onSubmit={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Save as template" })).not.toBeInTheDocument();
  });

  it("disables the save trigger below the minimum brief length, enables it above", () => {
    const { rerender } = render(
      <Composer value="" onChange={noop} onSubmit={vi.fn()} onSaveTemplate={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Save as template" })).toBeDisabled();

    rerender(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        onSaveTemplate={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Save as template" })).toBeEnabled();
  });

  it("calls onSaveTemplate with the current session models on click", () => {
    const onSaveTemplate = vi.fn();
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        onSaveTemplate={onSaveTemplate}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save as template" }));
    expect(onSaveTemplate).toHaveBeenCalledWith({});
  });

  it("applies loadTemplate's models to the session, visible in the model picker trigger", () => {
    render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        loadTemplate={{ token: "tpl_1:1", models: { orchestrator: "gpt-5.5" } }}
      />,
    );
    expect(screen.getByRole("button", { name: /GPT-5\.5/ })).toBeInTheDocument();
  });

  it("re-applies when the token changes, replacing a prior template's models", () => {
    const { rerender } = render(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        loadTemplate={{ token: "tpl_1:1", models: { orchestrator: "gpt-5.5" } }}
      />,
    );
    expect(screen.getByRole("button", { name: /GPT-5\.5/ })).toBeInTheDocument();

    rerender(
      <Composer
        value="A long enough brief to pass validation"
        onChange={noop}
        onSubmit={vi.fn()}
        loadTemplate={{ token: "tpl_2:1", models: {} }}
      />,
    );
    // an empty override map falls back to the orchestrator's own default model
    expect(screen.getByRole("button", { name: /Claude Opus 5/ })).toBeInTheDocument();
  });
});
