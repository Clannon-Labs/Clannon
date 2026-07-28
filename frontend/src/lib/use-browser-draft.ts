"use client";

import { useCallback, useSyncExternalStore } from "react";
import { readTextDraft, writeTextDraft } from "@/lib/browser-drafts";

const listeners = new Map<string, Set<() => void>>();
const fallbackDrafts = new Map<string, string>();

function emit(key: string) {
  listeners.get(key)?.forEach((notify) => notify());
}

function subscribe(key: string | null, notify: () => void): () => void {
  if (!key) return () => {};
  const set = listeners.get(key) ?? new Set<() => void>();
  set.add(notify);
  listeners.set(key, set);
  return () => {
    set.delete(notify);
    if (set.size === 0) listeners.delete(key);
  };
}

export function saveBrowserTextDraft(key: string, value: string): void {
  if (value.trim()) fallbackDrafts.set(key, value);
  else fallbackDrafts.delete(key);
  try {
    writeTextDraft(sessionStorage, key, value);
  } catch {
    /* In-memory fallback keeps this tab usable when storage is blocked. */
  }
  emit(key);
}

export function useBrowserTextDraft(
  key: string | null,
): readonly [string, (value: string) => void] {
  const subscribeToKey = useCallback(
    (notify: () => void) => subscribe(key, notify),
    [key],
  );
  const getSnapshot = useCallback(() => {
    if (!key) return "";
    try {
      const stored = readTextDraft(sessionStorage, key);
      if (stored) fallbackDrafts.set(key, stored);
      return stored || fallbackDrafts.get(key) || "";
    } catch {
      return fallbackDrafts.get(key) || "";
    }
  }, [key]);
  const value = useSyncExternalStore(subscribeToKey, getSnapshot, () => "");
  const setValue = useCallback(
    (next: string) => {
      if (key) saveBrowserTextDraft(key, next);
    },
    [key],
  );
  return [value, setValue] as const;
}
