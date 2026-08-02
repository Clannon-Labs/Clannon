import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTemplates } from "@/lib/use-templates";

/**
 * `templates.test.ts` covers the pure storage functions; this covers the
 * `useSyncExternalStore` wiring itself, which is where the real bug lived —
 * a fresh `[]` literal returned from `getSnapshot()` on every call loops
 * React forever (caught live on `/app` during a cold page load, where
 * `userId` is briefly undefined before auth resolves — never hit by a test
 * that only ever passed a real user id).
 */
describe("useTemplates", () => {
  it("returns a stable empty-array reference when there's no user yet, instead of looping", () => {
    // renderHook itself would throw ("Maximum update depth exceeded") if
    // getSnapshot returned a new reference each call — the assertion below
    // just documents why, once the render already proved it doesn't loop.
    const { result } = renderHook(() => useTemplates(undefined));
    expect(result.current.templates).toEqual([]);
  });

  it("returns a stable empty-array reference for a null user id too", () => {
    const { result } = renderHook(() => useTemplates(null));
    expect(result.current.templates).toEqual([]);
  });

  it("reads a real user's saved templates without looping", () => {
    localStorage.setItem(
      "clannon.templates.u1",
      JSON.stringify([{ id: "t1", name: "A", brief: "A", createdAt: "2026-01-01T00:00:00Z" }]),
    );
    const { result } = renderHook(() => useTemplates("u1"));
    expect(result.current.templates).toHaveLength(1);
    localStorage.removeItem("clannon.templates.u1");
  });
});
