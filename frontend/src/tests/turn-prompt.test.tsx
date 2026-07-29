import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TurnPrompt } from "@/components/app/turn-prompt";
import type { Run } from "@/lib/api";

const copyText = vi.fn().mockResolvedValue(undefined);
vi.mock("@/lib/copy-text", () => ({
  copyText: (text: string) => copyText(text),
}));

function turn(overrides: Partial<Run> = {}): Run {
  return {
    id: "run_1",
    title: "Original prompt",
    brief: "Research the original market question.",
    status: "delivered",
    createdAt: "2026-07-29T12:00:00.000Z",
    tokensUsed: 100,
    expertCount: 1,
    decisionLog: [],
    experts: [],
    sources: [],
    artifacts: [],
    inputs: [],
    ...overrides,
  };
}

describe("TurnPrompt", () => {
  it("reveals stable copy and edit actions from the sent prompt", () => {
    render(<TurnPrompt turn={turn()} onRevise={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Research the original market question/ }));
    expect(screen.getByRole("button", { name: "Copy sent prompt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit sent prompt" })).toBeInTheDocument();
  });

  it("copies the exact prompt client-side", async () => {
    render(<TurnPrompt turn={turn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Research the original market question/ }));
    fireEvent.click(screen.getByRole("button", { name: "Copy sent prompt" }));
    await waitFor(() =>
      expect(copyText).toHaveBeenCalledWith("Research the original market question."),
    );
  });

  it("edits in place and explains the context cut before submission", async () => {
    const revise = vi.fn().mockResolvedValue(undefined);
    render(<TurnPrompt turn={turn()} laterTurnCount={9} onRevise={revise} />);

    fireEvent.click(screen.getByRole("button", { name: /Research the original market question/ }));
    fireEvent.click(screen.getByRole("button", { name: "Edit sent prompt" }));

    const editor = screen.getByRole("textbox", { name: "Edit sent prompt" });
    expect(editor).toHaveValue("Research the original market question.");
    expect(
      screen.getByText(/9 later turns stay in history but won't enter the new conversation/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Saved memory remains/)).toBeInTheDocument();

    fireEvent.change(editor, { target: { value: "Research the corrected market question." } });
    fireEvent.click(screen.getByRole("button", { name: "Restart from here" }));

    await waitFor(() =>
      expect(revise).toHaveBeenCalledWith(
        "run_1",
        "Research the corrected market question.",
      ),
    );
  });

  it("keeps live prompts copyable without offering a revision", () => {
    render(<TurnPrompt turn={turn({ status: "orchestrating" })} />);
    fireEvent.click(screen.getByRole("button", { name: /Research the original market question/ }));
    expect(screen.getByRole("button", { name: "Copy sent prompt" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit sent prompt" })).not.toBeInTheDocument();
  });
});
