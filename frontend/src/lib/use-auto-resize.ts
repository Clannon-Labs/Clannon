"use client";

import { useEffect, useLayoutEffect, useRef } from "react";

// useLayoutEffect warns when it runs during SSR; fall back to useEffect there so
// the resize still happens on the client without the console noise.
const useIsoLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * Grow a textarea to fit its content, up to `maxPx` (after which it scrolls).
 * Pass the current controlled value so it re-measures on every change —
 * including programmatic ones, like clicking an example chip that fills the box.
 * A CSS `min-h-*` on the element sets the floor.
 */
export function useAutoResize(value: string, maxPx = 320) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useIsoLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto"; // shrink first so the box can also get smaller
    el.style.height = `${Math.min(el.scrollHeight, maxPx)}px`;
  }, [value, maxPx]);
  return ref;
}
