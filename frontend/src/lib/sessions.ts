import type { RunSummary } from "@/lib/api";

/** One conversation: the turns that share a sessionId, collapsed to a single
 *  entry. The title is the original ask; the link target is the newest turn
 *  (which renders the whole thread); counts/tokens aggregate across turns. */
export interface SessionEntry {
  sessionId: string;
  title: string; // the original ask — the session's topic
  latestId: string; // newest turn; the link target
  status: RunSummary["status"];
  createdAt: string; // latest activity
  turnCount: number;
  tokensUsed: number;
  expertCount: number;
}

/** Group runs into sessions: turns sharing a sessionId become one entry,
 *  newest session first. Shared by the workspace list and the sidebar rail. */
export function groupBySession(runs: RunSummary[] | undefined): SessionEntry[] {
  if (!runs) return [];
  const groups = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const sid = run.sessionId ?? run.id;
    const bucket = groups.get(sid);
    if (bucket) bucket.push(run);
    else groups.set(sid, [run]);
  }
  return [...groups.values()]
    .map((turns) => {
      const ordered = [...turns].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
      const first = ordered[0];
      const latest = ordered[ordered.length - 1];
      return {
        sessionId: first.sessionId ?? first.id,
        title: first.title,
        latestId: latest.id,
        status: latest.status,
        createdAt: latest.createdAt,
        turnCount: ordered.length,
        tokensUsed: ordered.reduce((sum, t) => sum + t.tokensUsed, 0),
        expertCount: ordered.reduce((sum, t) => sum + t.expertCount, 0),
      };
    })
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}
