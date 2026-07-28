const DRAFT_PREFIX = "clannon.workspace-draft";
const REPLY_PREFIX = "clannon.run-reply";
const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000;

interface TextDraft {
  value: string;
  updatedAt: number;
}

export function workspaceDraftKey(userId: string, projectId?: string): string {
  return `${DRAFT_PREFIX}.${userId}.${projectId ?? "unscoped"}`;
}

export function runReplyDraftKey(userId: string, runId: string): string {
  return `${REPLY_PREFIX}.${userId}.${runId}`;
}

export function readTextDraft(
  storage: Pick<Storage, "getItem" | "removeItem">,
  key: string,
  now = Date.now(),
): string {
  try {
    const raw = storage.getItem(key);
    if (!raw) return "";
    const draft = JSON.parse(raw) as Partial<TextDraft>;
    if (
      typeof draft.value !== "string" ||
      typeof draft.updatedAt !== "number" ||
      now - draft.updatedAt > DRAFT_MAX_AGE_MS
    ) {
      storage.removeItem(key);
      return "";
    }
    return draft.value;
  } catch {
    storage.removeItem(key);
    return "";
  }
}

export function writeTextDraft(
  storage: Pick<Storage, "setItem" | "removeItem">,
  key: string,
  value: string,
): void {
  if (!value.trim()) {
    storage.removeItem(key);
    return;
  }
  storage.setItem(key, JSON.stringify({ value, updatedAt: Date.now() } satisfies TextDraft));
}
