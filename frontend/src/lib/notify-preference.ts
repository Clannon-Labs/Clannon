"use client";

import { useSyncExternalStore } from "react";

/**
 * Whether the user has opted into a real OS notification when a run finishes
 * in a backgrounded tab. Client-only, no backend field — same shape as
 * `theme.tsx`'s external store. Kept separate from whether the browser has
 * actually granted permission: those two can disagree (user flips this on,
 * then blocks notifications in browser settings later), and the UI needs to
 * show that mismatch rather than silently doing nothing.
 */

const STORAGE_KEY = "clannon.notify.runsComplete";

const listeners = new Set<() => void>();

function readEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeEnabled(value: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
  } catch {
    /* storage unavailable — the choice still holds for this page view */
  }
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  return () => listeners.delete(notify);
}

/** `null` when the API doesn't exist (SSR, or a browser without Notification
 *  support) — distinct from "default"/"denied", both real permission states. */
export function notificationPermission(): NotificationPermission | null {
  if (typeof window === "undefined" || typeof Notification === "undefined") return null;
  return Notification.permission;
}

export function useNotifyPreference() {
  const enabled = useSyncExternalStore(subscribe, readEnabled, () => false);
  return {
    /** The user's stored choice. Only meaningful alongside `permission` — an
     *  enabled preference with a denied/default permission means nothing
     *  will actually fire, and the UI should say so. */
    enabled,
    permission: notificationPermission(),
    /** User-gesture only: browsers require a real click to show the
     *  permission prompt at all, and silently no-op or auto-deny otherwise. */
    async requestEnable(): Promise<boolean> {
      if (typeof window === "undefined" || typeof Notification === "undefined") return false;
      const result =
        Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
      const granted = result === "granted";
      writeEnabled(granted);
      return granted;
    },
    disable() {
      writeEnabled(false);
    },
  };
}
