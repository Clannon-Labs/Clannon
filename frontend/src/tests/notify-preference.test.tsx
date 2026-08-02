import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useNotifyPreference, notificationPermission } from "@/lib/notify-preference";

const STORAGE_KEY = "clannon.notify.runsComplete";

function mockNotification(permission: NotificationPermission, requestResult?: NotificationPermission) {
  const requestPermission = vi.fn().mockResolvedValue(requestResult ?? permission);
  Object.defineProperty(window, "Notification", {
    configurable: true,
    value: { permission, requestPermission },
  });
  return requestPermission;
}

// exercises the hook through a real render — useSyncExternalStore requires
// an actual React render context, so a bare function call would throw
// "Invalid hook call"
function Probe() {
  const { enabled, permission, requestEnable, disable } = useNotifyPreference();
  return (
    <div>
      <span data-testid="enabled">{String(enabled)}</span>
      <span data-testid="permission">{String(permission)}</span>
      <button type="button" onClick={() => requestEnable()}>
        request
      </button>
      <button type="button" onClick={() => disable()}>
        disable
      </button>
    </div>
  );
}

describe("notificationPermission", () => {
  const original = (window as unknown as { Notification?: unknown }).Notification;

  afterEach(() => {
    if (original) {
      Object.defineProperty(window, "Notification", { configurable: true, value: original });
    } else {
      delete (window as unknown as { Notification?: unknown }).Notification;
    }
    localStorage.clear();
  });

  it("returns null when the browser has no Notification API", () => {
    delete (window as unknown as { Notification?: unknown }).Notification;
    expect(notificationPermission()).toBeNull();
  });

  it("returns the browser's current permission otherwise", () => {
    mockNotification("default");
    expect(notificationPermission()).toBe("default");
  });
});

describe("useNotifyPreference", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("defaults to disabled", () => {
    mockNotification("default");
    render(<Probe />);
    expect(screen.getByTestId("enabled")).toHaveTextContent("false");
  });

  it("requestEnable persists true only when the browser actually grants permission", async () => {
    mockNotification("default", "granted");
    render(<Probe />);
    fireEvent.click(screen.getByRole("button", { name: "request" }));
    await waitFor(() => expect(screen.getByTestId("enabled")).toHaveTextContent("true"));
    expect(localStorage.getItem(STORAGE_KEY)).toBe("1");
  });

  it("requestEnable does not persist true when the browser denies", async () => {
    mockNotification("default", "denied");
    render(<Probe />);
    fireEvent.click(screen.getByRole("button", { name: "request" }));
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).toBe("0"));
    expect(screen.getByTestId("enabled")).toHaveTextContent("false");
  });

  it("disable() clears an already-stored preference", async () => {
    localStorage.setItem(STORAGE_KEY, "1");
    mockNotification("granted");
    render(<Probe />);
    expect(screen.getByTestId("enabled")).toHaveTextContent("true");
    fireEvent.click(screen.getByRole("button", { name: "disable" }));
    expect(screen.getByTestId("enabled")).toHaveTextContent("false");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("0");
  });
});
