"use client";

import { useEffect, type RefObject } from "react";

/**
 * Focus utilities for the hand-built overlay primitives (drawer, popovers,
 * role=menu surfaces). The native <dialog> covers modals; these cover
 * everything that can't be a <dialog>. Dependency-free on purpose.
 */

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

/**
 * Trap Tab focus inside `ref` while `active`; move focus in on activation
 * and hand it back to whatever had it before on deactivation. Pass
 * `initialFocus` to aim the first focus (falls back to the first focusable).
 */
export function useFocusTrap(
  active: boolean,
  ref: RefObject<HTMLElement | null>,
  initialFocus?: string,
) {
  useEffect(() => {
    if (!active) return;
    const container = ref.current;
    if (!container) return;
    const previous = document.activeElement as HTMLElement | null;

    const target =
      (initialFocus && container.querySelector<HTMLElement>(initialFocus)) ||
      focusables(container)[0] ||
      container;
    target.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Tab" || !container) return;
      const items = focusables(container);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;
      if (e.shiftKey && (current === first || current === container)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && current === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      previous?.focus?.();
    };
  }, [active, ref, initialFocus]);
}

/**
 * Lock body scroll while an overlay is open (mobile drawer, sheet menus).
 * Restores the previous overflow on close.
 */
export function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [active]);
}

const MENU_ITEMS =
  '[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';

/**
 * Keyboard model for a `role="menu"` popover: Arrow keys rove across the
 * menuitem-role children (menuitem / menuitemradio / menuitemcheckbox),
 * Home/End jump, and focus lands on the first item when the menu opens.
 * Attach the returned handler to the menu element's onKeyDown. Escape/close
 * stays the caller's job (it usually also restores focus to the trigger).
 */
export function menuKeyboardHandler(container: HTMLElement | null) {
  return (e: React.KeyboardEvent) => {
    if (!container) return;
    const items = Array.from(
      container.querySelectorAll<HTMLElement>(MENU_ITEMS),
    ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
    if (items.length === 0) return;
    const index = items.indexOf(document.activeElement as HTMLElement);
    let next = -1;
    if (e.key === "ArrowDown") next = index < items.length - 1 ? index + 1 : 0;
    else if (e.key === "ArrowUp") next = index > 0 ? index - 1 : items.length - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    if (next === -1) return;
    e.preventDefault();
    items[next].focus();
  };
}
