/**
 * Saved templates — a brief you expect to reuse, captured with enough of its
 * shape to actually save time next time: the text, any model overrides you'd
 * customized, and which project it was written for. Account-wide for v1 (not
 * per-project — the simpler of two reasonable scopes, and the one that
 * doesn't need a scoping decision on every save). Local-storage only: this
 * does not sync across devices/browsers. Syncing would mean a real backend
 * contract, which is a proposal, not a default — noted here so it isn't
 * mistaken for an oversight.
 */

const TEMPLATE_PREFIX = "clannon.templates";
const NAME_MAX = 60;

export interface SavedTemplate {
  id: string;
  /** Short label shown on the card — derived from the brief unless the user
   *  typed their own when saving. */
  name: string;
  brief: string;
  /** Session model overrides at save time, if any were customized. */
  models?: Record<string, string>;
  /** The project this was written for, if any — reused on load, never
   *  forced (the project may since be gone; loading falls back to "no
   *  project" rather than failing). */
  projectId?: string;
  createdAt: string;
}

function templatesKey(userId: string): string {
  return `${TEMPLATE_PREFIX}.${userId}`;
}

/** First clause or ~60 chars of a brief, whichever is shorter — the same
 *  "read the first meaningful chunk" heuristic a person would use to name
 *  their own saved prompt. */
export function deriveTemplateName(brief: string): string {
  const trimmed = brief.trim();
  const firstClause = trimmed.split(/[.!?\n]/)[0]?.trim() ?? trimmed;
  const base = firstClause.length > 0 ? firstClause : trimmed;
  if (base.length <= NAME_MAX) return base;
  return `${base.slice(0, NAME_MAX - 1).replace(/\s+\S*$/, "").trimEnd()}…`;
}

export function readTemplates(storage: Pick<Storage, "getItem">, userId: string): SavedTemplate[] {
  try {
    const raw = storage.getItem(templatesKey(userId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SavedTemplate[]) : [];
  } catch {
    return [];
  }
}

function writeTemplates(
  storage: Pick<Storage, "setItem">,
  userId: string,
  templates: SavedTemplate[],
): void {
  storage.setItem(templatesKey(userId), JSON.stringify(templates));
}

export function saveTemplate(
  storage: Pick<Storage, "getItem" | "setItem">,
  userId: string,
  input: { brief: string; name?: string; models?: Record<string, string>; projectId?: string },
): SavedTemplate {
  const trimmedBrief = input.brief.trim();
  const template: SavedTemplate = {
    id: `tpl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    name: input.name?.trim() || deriveTemplateName(trimmedBrief),
    brief: trimmedBrief,
    models: input.models && Object.keys(input.models).length ? input.models : undefined,
    projectId: input.projectId,
    createdAt: new Date().toISOString(),
  };
  // newest first — the one you just saved is the one you're most likely to
  // want to double-check or reuse again immediately
  writeTemplates(storage, userId, [template, ...readTemplates(storage, userId)]);
  return template;
}

export function deleteTemplate(
  storage: Pick<Storage, "getItem" | "setItem">,
  userId: string,
  id: string,
): void {
  writeTemplates(
    storage,
    userId,
    readTemplates(storage, userId).filter((t) => t.id !== id),
  );
}
