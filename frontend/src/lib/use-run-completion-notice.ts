"use client";

import { useEffect, useRef } from "react";
import type { RunStatus } from "@/lib/api/types";
import { useNotifyPreference } from "@/lib/notify-preference";

type NoticeKind = "delivered" | "partial" | "blocked" | "failed";

const COPY: Record<NoticeKind, { title: string; tabPrefix: string }> = {
  delivered: { title: "Report ready", tabPrefix: "✓" },
  partial: { title: "Report ready — partial", tabPrefix: "✓" },
  blocked: { title: "Run blocked", tabPrefix: "!" },
  failed: { title: "Run failed", tabPrefix: "!" },
};

function kindFor(status: RunStatus, isPartial: boolean): NoticeKind | null {
  if (status === "delivered") return isPartial ? "partial" : "delivered";
  if (status === "blocked") return "blocked";
  if (status === "failed") return "failed";
  // cancelled is user-initiated — they already know, no need to interrupt them
  return null;
}

/**
 * Notifies the user when a run finishes while its tab is backgrounded — the
 * gap this closes: runs can take minutes (sequential orchestrator rounds),
 * and today nothing tells you when one's done except coming back to look.
 * Two independent layers, deliberately: the tab-title flash needs no
 * permission and always works; the real OS notification is opt-in (Settings
 * → Account → Notifications) since browsers gate it behind a user gesture.
 *
 * Scoped to "this run's page is open in a background/unfocused tab" — the
 * SSE stream this hook rides on only runs while `RunPage` is mounted, so
 * navigating elsewhere *within* Clannon while a run is in flight stops
 * tracking it, same as it already stops rendering it live. Notifying across
 * the whole app regardless of what page is open would need a
 * separate always-on subscription — a real but separate piece of work, not
 * folded in here to avoid a second, parallel way of tracking run state.
 */
export function useRunCompletionNotice(
  runId: string | undefined,
  runTitle: string | undefined,
  status: RunStatus,
  isTerminal: boolean,
  isPartial: boolean,
) {
  const { enabled, permission } = useNotifyPreference();
  // null = "not yet observed" — seeds silently on mount instead of firing for
  // a run that was ALREADY terminal when this page opened (matches the
  // `prevReportDone` idiom already used for the report auto-scroll in
  // RunPage — same shape, same reason: only react to a live transition).
  const wasTerminal = useRef<boolean | null>(null);
  const originalTitle = useRef<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    if (wasTerminal.current === null) {
      wasTerminal.current = isTerminal;
      return;
    }
    const justFinished = !wasTerminal.current && isTerminal;
    wasTerminal.current = isTerminal;
    if (!justFinished || typeof document === "undefined" || !document.hidden) return;

    const kind = kindFor(status, isPartial);
    if (!kind) return;
    const { title, tabPrefix } = COPY[kind];

    originalTitle.current ??= document.title;
    document.title = `${tabPrefix} ${title} · Clannon`;

    if (enabled && permission === "granted") {
      const n = new Notification(title, {
        body: runTitle ?? "Your run finished.",
        tag: runId,
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
    }
  }, [runId, runTitle, status, isTerminal, isPartial, enabled, permission]);

  // restore the real tab title once the user actually comes back to it, or
  // when this run's page unmounts (route change) — a flashed title that
  // outlives the reason for it is just noise the next time you glance at the tab
  useEffect(() => {
    function restore() {
      if (!document.hidden && originalTitle.current) {
        document.title = originalTitle.current;
        originalTitle.current = null;
      }
    }
    document.addEventListener("visibilitychange", restore);
    return () => {
      document.removeEventListener("visibilitychange", restore);
      if (originalTitle.current) {
        document.title = originalTitle.current;
        originalTitle.current = null;
      }
    };
  }, []);
}
