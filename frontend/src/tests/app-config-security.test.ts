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
  });

  it("requires explicit mock opt-in and rejects unknown modes", () => {
    expect(resolveApiMode("mock")).toBe("mock");
    expect(resolveApiMode("http")).toBe("http");
    expect(() => resolveApiMode("htp")).toThrow(/must be exactly/);
    expect(() => resolveApiMode("MOCK")).toThrow(/must be exactly/);
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
  ])("rejects dangerous or non-absolute URL %s", (value) => {
    expect(normalizeHttpUrl(value)).toBeNull();
  });

  it.each([
    ["https://example.com", "https://example.com/"],
    ["http://localhost:8000/path?q=1#part", "http://localhost:8000/path?q=1#part"],
  ])("preserves normalized HTTP(S) URL %s", (value, expected) => {
    expect(normalizeHttpUrl(value)).toBe(expected);
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
