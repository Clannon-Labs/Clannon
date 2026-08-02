import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { useRunCompletionNotice } from "@/lib/use-run-completion-notice";
import type { RunStatus } from "@/lib/api/types";

const STORAGE_KEY = "clannon.notify.runsComplete";

function setHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
}

function Host({ status, isTerminal, isPartial }: { status: RunStatus; isTerminal: boolean; isPartial: boolean }) {
  useRunCompletionNotice("run_1", "UK market entry", status, isTerminal, isPartial);
  return null;
}

describe("useRunCompletionNotice", () => {
  const originalTitle = document.title;
  let notificationSpy: (title: string, options: NotificationOptions) => void;

  beforeEach(() => {
    document.title = "Clannon";
    setHidden(false);
    localStorage.clear();
    notificationSpy = vi.fn();
    class FakeNotification {
      static permission: NotificationPermission = "granted";
      onclick: (() => void) | null = null;
      constructor(title: string, options: NotificationOptions) {
        notificationSpy(title, options);
      }
      close() {}
    }
    Object.defineProperty(window, "Notification", { configurable: true, value: FakeNotification });
  });

  afterEach(() => {
    document.title = originalTitle;
    setHidden(false);
  });

  it("does nothing on initial mount even if the run is already terminal", () => {
    setHidden(true);
    render(<Host status="delivered" isTerminal isPartial={false} />);
    expect(document.title).toBe("Clannon");
    expect(notificationSpy).not.toHaveBeenCalled();
  });

  it("flashes the tab title on a live transition to terminal while hidden", () => {
    setHidden(true);
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(document.title).toBe("✓ Report ready · Clannon");
  });

  it("does not touch the title when the tab is visible — the user is already watching", () => {
    setHidden(false);
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(document.title).toBe("Clannon");
  });

  it("does not notify on cancelled — user-initiated, not worth interrupting for", () => {
    setHidden(true);
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="cancelled" isTerminal isPartial={false} />);
    expect(document.title).toBe("Clannon");
    expect(notificationSpy).not.toHaveBeenCalled();
  });

  it("uses the partial-aware and failure copy correctly", () => {
    setHidden(true);
    const partial = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    partial.rerender(<Host status="delivered" isTerminal isPartial />);
    expect(document.title).toBe("✓ Report ready — partial · Clannon");
    partial.unmount();

    document.title = "Clannon";
    const failed = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    failed.rerender(<Host status="failed" isTerminal isPartial={false} />);
    expect(document.title).toBe("! Run failed · Clannon");
  });

  it("restores the original title once the tab becomes visible again", () => {
    setHidden(true);
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(document.title).toBe("✓ Report ready · Clannon");

    setHidden(false);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(document.title).toBe("Clannon");
  });

  it("restores the title on unmount even if the tab never came back", () => {
    setHidden(true);
    const { rerender, unmount } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(document.title).toBe("✓ Report ready · Clannon");
    unmount();
    expect(document.title).toBe("Clannon");
  });

  it("fires a real Notification only when the stored preference is enabled and permission is granted", () => {
    setHidden(true);
    localStorage.setItem(STORAGE_KEY, "1");
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(notificationSpy).toHaveBeenCalledOnce();
    expect(notificationSpy).toHaveBeenCalledWith(
      "Report ready",
      expect.objectContaining({ body: "UK market entry", tag: "run_1" }),
    );
  });

  it("does not fire a real Notification when the preference is off, even while hidden", () => {
    setHidden(true);
    localStorage.setItem(STORAGE_KEY, "0");
    const { rerender } = render(<Host status="orchestrating" isTerminal={false} isPartial={false} />);
    rerender(<Host status="delivered" isTerminal isPartial={false} />);
    expect(notificationSpy).not.toHaveBeenCalled();
    // the title flash still happens — it needs no permission at all
    expect(document.title).toBe("✓ Report ready · Clannon");
  });
});
