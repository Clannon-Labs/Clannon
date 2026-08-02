"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  deleteTemplate,
  readTemplates,
  saveTemplate,
  type SavedTemplate,
} from "@/lib/templates";

const listeners = new Map<string, Set<() => void>>();
// useSyncExternalStore requires getSnapshot to return the same reference
// when nothing changed — readTemplates() reparses JSON every call, which
// otherwise loops the render forever. Cache one snapshot per user, dropped
// whenever save/delete actually touches storage.
const snapshotCache = new Map<string, SavedTemplate[]>();
// same reasoning applies to the no-user case below: a fresh `[]` literal on
// every call is a fresh reference too, and loops just the same.
const EMPTY_TEMPLATES: SavedTemplate[] = [];

function emit(userId: string) {
  snapshotCache.delete(userId);
  listeners.get(userId)?.forEach((notify) => notify());
}

function subscribe(userId: string | null, notify: () => void): () => void {
  if (!userId) return () => {};
  const set = listeners.get(userId) ?? new Set<() => void>();
  set.add(notify);
  listeners.set(userId, set);
  return () => {
    set.delete(notify);
    if (set.size === 0) listeners.delete(userId);
  };
}

/**
 * The account's saved templates — reactive, so saving or deleting one
 * updates every mounted list immediately (same `useSyncExternalStore`
 * pattern as `use-browser-draft.ts`). `userId` is nullable so callers don't
 * need to guard on auth state loading first; the list is simply empty.
 */
export function useTemplates(userId: string | undefined | null) {
  const key = userId ?? null;
  const subscribeToKey = useCallback(
    (notify: () => void) => subscribe(key, notify),
    [key],
  );
  const getSnapshot = useCallback(() => {
    if (!key) return EMPTY_TEMPLATES;
    const cached = snapshotCache.get(key);
    if (cached) return cached;
    let fresh: SavedTemplate[];
    try {
      fresh = readTemplates(localStorage, key);
    } catch {
      fresh = [];
    }
    snapshotCache.set(key, fresh);
    return fresh;
  }, [key]);
  const templates = useSyncExternalStore(subscribeToKey, getSnapshot, () => EMPTY_TEMPLATES);

  const save = useCallback(
    (input: { brief: string; name?: string; models?: Record<string, string>; projectId?: string }) => {
      if (!key) return null;
      try {
        const template = saveTemplate(localStorage, key, input);
        emit(key);
        return template;
      } catch {
        return null; // storage blocked/full — saving a template is a nicety, never worth throwing over
      }
    },
    [key],
  );

  const remove = useCallback(
    (id: string) => {
      if (!key) return;
      try {
        deleteTemplate(localStorage, key, id);
        emit(key);
      } catch {
        /* storage blocked — nothing to reconcile, the in-memory list already reflects intent */
      }
    },
    [key],
  );

  return { templates, save, remove };
}
