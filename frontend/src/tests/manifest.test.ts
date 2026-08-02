import { describe, it, expect } from "vitest";
import manifest from "@/app/manifest";

/**
 * Chrome's install-prompt criteria (and the maskable-icon spec) need real
 * 192/512 entries with the right `purpose` values — a single oddly-sized
 * icon (the previous state here: one 305x305 "any" entry) technically
 * satisfies the MetadataRoute.Manifest type but fails real installability.
 */
describe("manifest", () => {
  const icons = manifest().icons ?? [];

  it("has a 192x192 and a 512x512 icon with purpose any", () => {
    const any192 = icons.find((i) => i.sizes === "192x192" && i.purpose === "any");
    const any512 = icons.find((i) => i.sizes === "512x512" && i.purpose === "any");
    expect(any192).toBeDefined();
    expect(any512).toBeDefined();
  });

  it("has a maskable 512x512 icon for adaptive home-screen shapes", () => {
    const maskable = icons.find((i) => i.sizes === "512x512" && i.purpose === "maskable");
    expect(maskable).toBeDefined();
  });

  it("every icon entry has a real image/png src", () => {
    for (const icon of icons) {
      expect(icon.src).toMatch(/\.png$/);
      expect(icon.type).toBe("image/png");
    }
  });
});
