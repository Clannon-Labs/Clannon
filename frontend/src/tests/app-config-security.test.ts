import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD, PHASE_PRODUCTION_SERVER } from "next/constants";
import { describe, expect, it } from "vitest";
import { resolveApiMode } from "@/config/api-mode";
import {
  normalizeHttpBaseUrl,
  normalizeHttpUrl,
  requireHttpBaseUrl,
} from "@/config/url-policy";

describe("fail-safe API configuration", () => {
  it("uses HTTP when API mode is missing or empty", () => {
    expect(resolveApiMode(undefined, undefined)).toBe("http");
    expect(resolveApiMode("", undefined)).toBe("http");
    // Missing/empty is safe regardless of phase.
    expect(resolveApiMode(undefined, PHASE_PRODUCTION_BUILD)).toBe("http");
    expect(resolveApiMode("", PHASE_PRODUCTION_BUILD)).toBe("http");
  });

  it("requires explicit mock opt-in and rejects unknown modes", () => {
    expect(resolveApiMode("mock", PHASE_DEVELOPMENT_SERVER)).toBe("mock");
    expect(resolveApiMode("http", undefined)).toBe("http");
    expect(() => resolveApiMode("htp", undefined)).toThrow(/must be exactly/);
    expect(() => resolveApiMode("MOCK", undefined)).toThrow(/must be exactly/);
    // Case-mismatched/unknown values are rejected independent of phase.
    expect(() => resolveApiMode("MOCK", PHASE_PRODUCTION_BUILD)).toThrow(/must be exactly/);
    expect(() => resolveApiMode("htp", PHASE_DEVELOPMENT_SERVER)).toThrow(/must be exactly/);
  });

  it("F-01: rejects mock mode during a production build, accepts it elsewhere", () => {
    // production build phase + mock => rejected
    expect(() => resolveApiMode("mock", PHASE_PRODUCTION_BUILD)).toThrow(
      /not permitted during a production build/,
    );
    // production build phase + http => accepted
    expect(resolveApiMode("http", PHASE_PRODUCTION_BUILD)).toBe("http");
    // production build phase + missing/empty => http (safe default, not a rejection)
    expect(resolveApiMode(undefined, PHASE_PRODUCTION_BUILD)).toBe("http");
    expect(resolveApiMode("", PHASE_PRODUCTION_BUILD)).toBe("http");
    // non-production-build phase + explicit mock => accepted
    expect(resolveApiMode("mock", PHASE_DEVELOPMENT_SERVER)).toBe("mock");
    expect(resolveApiMode("mock", PHASE_PRODUCTION_SERVER)).toBe("mock");
    expect(resolveApiMode("mock", undefined)).toBe("mock");
  });

  it("F-01 regression: the phase gate does not depend on NODE_ENV, so a build flag that only rewrites NODE_ENV cannot bypass it", () => {
    // `next build --debug-prerender` forces NODE_ENV to "development" while
    // Next still runs the build as PHASE_PRODUCTION_BUILD (measured in
    // reports/frontend-audit/report_v3.md). Simulate that exact split: an
    // ambient/inlined NODE_ENV of "development" alongside the real
    // production-build phase must still reject mock.
    const originalNodeEnv = process.env.NODE_ENV;
    // @ts-expect-error -- test-only override of a readonly-typed env var
    process.env.NODE_ENV = "development";
    try {
      expect(() => resolveApiMode("mock", PHASE_PRODUCTION_BUILD)).toThrow(
        /not permitted during a production build/,
      );
    } finally {
      // @ts-expect-error -- restore test-only override
      process.env.NODE_ENV = originalNodeEnv;
    }
  });
});

describe("HTTP(S)-only URL policy", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "blob:https://clannon.com/id",
    "mailto:security@example.com",
    "//example.com/path",
    " https://example.com",
    "https://example.com ",
    "not a url",
    // Invalid host/port, existing coverage for the parser-rejection branch.
    "https://",
    "https://example.com:notaport",
  ])("rejects dangerous or non-absolute URL %s", (value) => {
    expect(normalizeHttpUrl(value)).toBeNull();
  });

  it.each([
    ["https://example.com", "https://example.com/"],
    ["http://localhost:8000/path?q=1#part", "http://localhost:8000/path?q=1#part"],
    // Safe percent-encoded path/query values must keep working.
    ["https://example.com/%20path?q=%3D", "https://example.com/%20path?q=%3D"],
    ["https://example.com/na%C3%AFve", "https://example.com/na%C3%AFve"],
  ])("preserves normalized HTTP(S) URL %s", (value, expected) => {
    expect(normalizeHttpUrl(value)).toBe(expected);
  });

  it.each([
    // username/password/userinfo, in every combination the parser accepts.
    "https://user:pass@example.com/report",
    "https://user@example.com/report",
    "https://:pass@example.com/report",
    "http://user:pass@localhost:8000/",
  ])("F-02: rejects credential-bearing URL %s", (value) => {
    expect(normalizeHttpUrl(value)).toBeNull();
  });

  it.each([
    // stray, truncated, and non-hex percent escapes the URL parser tolerates silently.
    "https://example.com/%zz",
    "https://example.com/%2",
    "https://example.com/%2g",
    "https://example.com/100%off",
    "https://example.com/%",
    "https://example.com/path?q=%gg",
  ])("F-02: rejects malformed percent escape %s", (value) => {
    expect(normalizeHttpUrl(value)).toBeNull();
  });

  it("rejects ambiguous backend base URLs before CSP or fetch interpolation", () => {
    expect(normalizeHttpBaseUrl("https://api.clannon.com/")).toBe("https://api.clannon.com");
    expect(normalizeHttpBaseUrl("https://user:pass@api.clannon.com")).toBeNull();
    expect(normalizeHttpBaseUrl("https://api.clannon.com?source=other")).toBeNull();
    expect(() => requireHttpBaseUrl("javascript:alert(1)", "TEST_API_URL")).toThrow(
      /TEST_API_URL must be an absolute/,
    );
  });
});
