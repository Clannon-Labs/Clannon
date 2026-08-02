import { describe, it, expect } from "vitest";
import { deriveTemplateName, readTemplates, saveTemplate, deleteTemplate } from "@/lib/templates";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

describe("deriveTemplateName", () => {
  it("uses the first clause of the brief", () => {
    expect(deriveTemplateName("Draft a market note. Focus on pricing.")).toBe(
      "Draft a market note",
    );
  });

  it("falls back to a clamped prefix when there's no clause break", () => {
    const long = "a".repeat(80);
    const name = deriveTemplateName(long);
    expect(name.length).toBeLessThanOrEqual(60);
    expect(name.endsWith("…")).toBe(true);
  });
});

describe("saveTemplate / readTemplates / deleteTemplate", () => {
  it("saves newest-first and scopes storage by user", () => {
    const storage = memoryStorage();
    const first = saveTemplate(storage, "u1", { brief: "First brief" });
    const second = saveTemplate(storage, "u1", { brief: "Second brief" });
    expect(readTemplates(storage, "u1").map((t) => t.id)).toEqual([second.id, first.id]);
    expect(readTemplates(storage, "u2")).toEqual([]);
  });

  it("uses an explicit name over the derived one, and drops empty model overrides", () => {
    const storage = memoryStorage();
    const t = saveTemplate(storage, "u1", {
      brief: "Draft a market note.",
      name: "Weekly market note",
      models: {},
      projectId: "proj_1",
    });
    expect(t.name).toBe("Weekly market note");
    expect(t.models).toBeUndefined();
    expect(t.projectId).toBe("proj_1");
  });

  it("keeps real model overrides", () => {
    const storage = memoryStorage();
    const t = saveTemplate(storage, "u1", {
      brief: "Draft a market note.",
      models: { research: "gpt-5" },
    });
    expect(t.models).toEqual({ research: "gpt-5" });
  });

  it("deletes only the targeted template", () => {
    const storage = memoryStorage();
    const a = saveTemplate(storage, "u1", { brief: "A" });
    const b = saveTemplate(storage, "u1", { brief: "B" });
    deleteTemplate(storage, "u1", a.id);
    expect(readTemplates(storage, "u1").map((t) => t.id)).toEqual([b.id]);
  });

  it("degrades to an empty list rather than throwing on corrupt storage", () => {
    const storage = memoryStorage();
    storage.setItem("clannon.templates.u1", "{not json");
    expect(readTemplates(storage, "u1")).toEqual([]);
  });
});
