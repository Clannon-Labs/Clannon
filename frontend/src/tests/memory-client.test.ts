/**
 * Contract tests for the memory/wiki CRUD surface of ClannonClient, driven
 * against MockClient.
 *
 * These tests pin that the four operations the memory/wiki panel
 * (app/app/memory/page.tsx) wires to ClannonClient behave as the UI expects:
 *
 *   view   → listMemory returns entries with all required fields
 *   create → saveMemoryEntry (no id) creates and persists a new entry
 *   edit   → saveMemoryEntry (with id) mutates the existing entry in place
 *   delete → deleteMemoryEntry removes the entry from subsequent listMemory
 *
 * All tests are hermetic: MockClient only, no network, no backend.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { MockClient } from "@/lib/api/mock";
import { ApiError } from "@/lib/api/types";

let client: MockClient;

beforeEach(() => {
  client = new MockClient();
});

// ---- view: listMemory -------------------------------------------------------

describe("listMemory (view)", () => {
  it("returns seed entries with all required MemoryEntry fields", async () => {
    const entries = await client.listMemory();
    expect(entries.length).toBeGreaterThan(0);
    for (const e of entries) {
      expect(typeof e.id).toBe("string");
      expect(e.id.length).toBeGreaterThan(0);
      expect(["wiki", "semantic", "episodic", "procedural"]).toContain(e.tier);
      expect(typeof e.title).toBe("string");
      expect(typeof e.content).toBe("string");
      expect(typeof e.updatedAt).toBe("string");
    }
  });

  it("returns all four tiers in the seed data", async () => {
    const entries = await client.listMemory();
    const tiers = new Set(entries.map((e) => e.tier));
    expect(tiers.has("wiki")).toBe(true);
    expect(tiers.has("semantic")).toBe(true);
    expect(tiers.has("episodic")).toBe(true);
    expect(tiers.has("procedural")).toBe(true);
  });

  it("filters by projectId when supplied", async () => {
    const projectId = "proj_meridian";
    const scoped = await client.listMemory(projectId);
    expect(scoped.length).toBeGreaterThan(0);
    for (const e of scoped) {
      expect(e.projectId).toBe(projectId);
    }
  });

  it("returns an empty array when projectId has no entries", async () => {
    const entries = await client.listMemory("proj_does_not_exist");
    expect(entries).toHaveLength(0);
  });

  it("returns all entries across projects when projectId is omitted", async () => {
    const all = await client.listMemory();
    const scoped = await client.listMemory("proj_meridian");
    // All unscoped count >= one project's count
    expect(all.length).toBeGreaterThanOrEqual(scoped.length);
  });
});

// ---- create: saveMemoryEntry (no id) ----------------------------------------

describe("saveMemoryEntry (create)", () => {
  it("creates a new entry and returns it with a generated id", async () => {
    const entry = await client.saveMemoryEntry({
      tier: "wiki",
      title: "Client: ACME Corp — context",
      content: "A multinational widget manufacturer.",
    });
    expect(entry.id).toBeDefined();
    expect(entry.id.length).toBeGreaterThan(0);
    expect(entry.tier).toBe("wiki");
    expect(entry.title).toBe("Client: ACME Corp — context");
    expect(entry.content).toBe("A multinational widget manufacturer.");
    expect(entry.updatedAt).toBeDefined();
  });

  it("new entry is visible in subsequent listMemory", async () => {
    const before = await client.listMemory();
    await client.saveMemoryEntry({
      tier: "wiki",
      title: "New wiki fact",
      content: "Factual content here.",
    });
    const after = await client.listMemory();
    expect(after.length).toBe(before.length + 1);
  });

  it("scopes the new entry to the supplied projectId", async () => {
    const projectId = "proj_test_scope";
    const entry = await client.saveMemoryEntry(
      { tier: "wiki", title: "Scoped entry", content: "Content" },
      projectId,
    );
    expect(entry.projectId).toBe(projectId);
    const scoped = await client.listMemory(projectId);
    expect(scoped.find((e) => e.id === entry.id)).toBeDefined();
  });

  it("each created entry gets a unique id", async () => {
    const a = await client.saveMemoryEntry({ tier: "wiki", title: "Entry A", content: "A" });
    const b = await client.saveMemoryEntry({ tier: "wiki", title: "Entry B", content: "B" });
    expect(a.id).not.toBe(b.id);
  });
});

// ---- edit: saveMemoryEntry (with id) ----------------------------------------

describe("saveMemoryEntry (edit)", () => {
  it("updates an existing entry's title and content", async () => {
    const created = await client.saveMemoryEntry({
      tier: "wiki",
      title: "Original title",
      content: "Original content",
    });
    const updated = await client.saveMemoryEntry({
      id: created.id,
      tier: "wiki",
      title: "Updated title",
      content: "Updated content",
    });
    expect(updated.id).toBe(created.id);
    expect(updated.title).toBe("Updated title");
    expect(updated.content).toBe("Updated content");
  });

  it("persists the update: listMemory reflects the new title", async () => {
    const created = await client.saveMemoryEntry({
      tier: "wiki",
      title: "Before edit",
      content: "Old content",
    });
    await client.saveMemoryEntry({
      id: created.id,
      tier: "wiki",
      title: "After edit",
      content: "New content",
    });
    const entries = await client.listMemory();
    const found = entries.find((e) => e.id === created.id);
    expect(found?.title).toBe("After edit");
    expect(found?.content).toBe("New content");
  });

  it("edit sets a fresh updatedAt timestamp", async () => {
    const created = await client.saveMemoryEntry({
      tier: "wiki",
      title: "Title",
      content: "Content",
    });
    const originalUpdatedAt = created.updatedAt;
    const updated = await client.saveMemoryEntry({
      id: created.id,
      tier: "wiki",
      title: "Title",
      content: "New content",
    });
    // updatedAt must be a valid ISO string and at or after the original
    expect(new Date(updated.updatedAt).getTime()).toBeGreaterThanOrEqual(
      new Date(originalUpdatedAt).getTime(),
    );
  });

  it("throws ApiError 404 when editing a non-existent id", async () => {
    const err = await client
      .saveMemoryEntry({ id: "nonexistent_id", tier: "wiki", title: "X", content: "Y" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
  });
});

// ---- delete: deleteMemoryEntry ----------------------------------------------

describe("deleteMemoryEntry (delete)", () => {
  it("removes the entry from subsequent listMemory", async () => {
    const entry = await client.saveMemoryEntry({
      tier: "wiki",
      title: "To be deleted",
      content: "Temporary content",
    });
    await client.deleteMemoryEntry(entry.id);
    const entries = await client.listMemory();
    expect(entries.find((e) => e.id === entry.id)).toBeUndefined();
  });

  it("reduces the listMemory count by exactly one", async () => {
    const entry = await client.saveMemoryEntry({
      tier: "wiki",
      title: "Delete me",
      content: "Content",
    });
    const before = await client.listMemory();
    await client.deleteMemoryEntry(entry.id);
    const after = await client.listMemory();
    expect(after.length).toBe(before.length - 1);
  });

  it("is a no-op for a non-existent id (does not throw)", async () => {
    const before = await client.listMemory();
    await client.deleteMemoryEntry("nonexistent_id_xyz");
    const after = await client.listMemory();
    expect(after.length).toBe(before.length);
  });

  it("can delete a seed entry", async () => {
    const all = await client.listMemory();
    const seed = all[0];
    await client.deleteMemoryEntry(seed.id);
    const after = await client.listMemory();
    expect(after.find((e) => e.id === seed.id)).toBeUndefined();
  });
});

// ---- uploadMemoryFiles -------------------------------------------------------
//
// uploadMemoryFiles is the wiki bulk-import path (the "Upload files" button).
// Pin its key behaviours: valid markdown files become wiki entries, and obvious
// bad inputs are rejected before anything is persisted.

describe("uploadMemoryFiles", () => {
  function makeFile(name: string, content: string, type = "text/markdown"): File {
    return new File([content], name, { type });
  }

  it("creates a wiki entry for each uploaded .md file", async () => {
    const files = [
      makeFile("client-acme.md", "# ACME Corp\n\nA widget manufacturer."),
      makeFile("style-guide.md", "Use British English for UK deliverables."),
    ];
    const created = await client.uploadMemoryFiles(files);
    expect(created).toHaveLength(2);
    for (const e of created) {
      expect(e.tier).toBe("wiki");
      expect(e.id).toBeDefined();
    }
  });

  it("new entries appear in listMemory after upload", async () => {
    const before = await client.listMemory();
    const files = [makeFile("new-client.md", "New client facts here.")];
    await client.uploadMemoryFiles(files);
    const after = await client.listMemory();
    expect(after.length).toBe(before.length + 1);
  });

  it("rejects empty file list with ApiError 422", async () => {
    const err = await client.uploadMemoryFiles([]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
  });

  it("rejects files with a disallowed extension", async () => {
    const file = new File(["data"], "spreadsheet.xlsx", { type: "application/vnd.ms-excel" });
    const err = await client.uploadMemoryFiles([file]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
  });

  it("rejects files larger than 512 KB", async () => {
    const bigContent = "x".repeat(512 * 1024 + 1);
    const file = makeFile("huge.md", bigContent);
    const err = await client.uploadMemoryFiles([file]).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
  });

  it("rejects more than 10 files at once", async () => {
    const files = Array.from({ length: 11 }, (_, i) =>
      makeFile(`file${i}.md`, "content"),
    );
    const err = await client.uploadMemoryFiles(files).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
  });
});
