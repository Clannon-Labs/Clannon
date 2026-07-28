import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CompletionBadge, CompletionBanner } from "@/components/app/completion-status";

describe("CompletionBadge", () => {
  it("renders the Partial pill", () => {
    render(<CompletionBadge />);
    expect(screen.getByText("Partial")).toBeInTheDocument();
  });
});

describe("CompletionBanner", () => {
  it("names a timeout without calling it an error", () => {
    render(<CompletionBanner reason="timeout" onContinue={() => {}} />);
    expect(screen.getByText("Ran out of time before finishing")).toBeInTheDocument();
  });

  it("names a rate limit interruption", () => {
    render(<CompletionBanner reason="rate_limit" onContinue={() => {}} />);
    expect(screen.getByText("Interrupted by a rate limit")).toBeInTheDocument();
  });

  it("names an error interruption", () => {
    render(<CompletionBanner reason="error" onContinue={() => {}} />);
    expect(screen.getByText("Interrupted by an error")).toBeInTheDocument();
  });

  it("falls back to generic wording for an unclassified cause", () => {
    render(<CompletionBanner reason={null} onContinue={() => {}} />);
    expect(screen.getByText("Didn't finish everything planned")).toBeInTheDocument();
  });

  it("offers a concrete way forward that the caller controls", () => {
    const onContinue = vi.fn();
    render(<CompletionBanner reason="timeout" onContinue={onContinue} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue this run" }));
    expect(onContinue).toHaveBeenCalledOnce();
  });
});
