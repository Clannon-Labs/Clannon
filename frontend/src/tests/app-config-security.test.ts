import { describe, expect, it } from "vitest";
import { resolveApiMode } from "@/config/app.config";
import {
  normalizeHttpBaseUrl,
  normalizeHttpUrl,
  requireHttpBaseUrl,
} from "@/config/url-policy";

describe("fail-safe API configuration", () => {
  it("uses HTTP when API mode is missing or empty", () => {
    expect(resolveApiMode(undefined)).toBe("http");
    expect(resolveApiMode("")).toBe("http");
    // Missing/empty is safe regardless of environment.
    expect(resolveApiMode(undefined, "production")).toBe("http");
    expect(resolveApiMode("", "production")).toBe("http");
  });

  it("requires explicit mock opt-in and rejects unknown modes", () => {
    expect(resolveApiMode("mock", "development")).toBe("mock");
    expect(resolveApiMode("http")).toBe("http");
    expect(() => resolveApiMode("htp")).toThrow(/must be exactly/);
    expect(() => resolveApiMode("MOCK")).toThrow(/must be exactly/);
    // Case-mismatched/unknown values are rejected independent of environment.
    expect(() => resolveApiMode("MOCK", "production")).toThrow(/must be exactly/);
    expect(() => resolveApiMode("htp", "development")).toThrow(/must be exactly/);
  });

  it("F-01: rejects mock mode in production, accepts it elsewhere", () => {
    // production + mock => rejected
    expect(() => resolveApiMode("mock", "production")).toThrow(
      /not permitted when NODE_ENV=production/,
    );
    // production + http => accepted
    expect(resolveApiMode("http", "production")).toBe("http");
    // production + missing/empty => http (safe default, not a rejection)
    expect(resolveApiMode(undefined, "production")).toBe("http");
    expect(resolveApiMode("", "production")).toBe("http");
    // non-production + explicit mock => accepted
    expect(resolveApiMode("mock", "development")).toBe("mock");
    expect(resolveApiMode("mock", "test")).toBe("mock");
    expect(resolveApiMode("mock", undefined)).toBe("mock");
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
