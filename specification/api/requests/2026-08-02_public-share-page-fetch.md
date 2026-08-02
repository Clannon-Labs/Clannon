# Fetch a shared run's public-safe payload (unauthenticated)

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   OPEN
Blocking: no
```

## What UI this unblocks

A new public route, `/share/{token}` — outside `RequireAuth`, reachable by
anyone with the link, rendering the report, its verification state, and
downloadable artifacts. Not the run's chat thread, decision log, memory
context used, cost/token counts, or anything account-identifying. Paired
with `2026-08-02_run-share-link-create-revoke.md` (the create/revoke side);
this is the read side a stranger's browser actually calls.

## Proposed route

| | |
|---|---|
| Method | `GET` |
| Path | `/share/{token}` |
| Auth | **none** — the token itself is the credential, same trust model as any unguessable-link share (Perplexity/ChatGPT/Notion all do this) |

## Response

```ts
type PublicSharedRun = {
  title: string;
  report: string;               // markdown — same content as the owner's report tab
  verificationState: "grounded" | "unverified" | "partial"; // whatever the real enum is — see verification-status.tsx
  completionState?: "partial";
  completionReason?: string;
  artifacts: { name: string; mime: string; size: number }[]; // metadata only — see below for the actual bytes
  deliveredAt: string; // ISO — so the public page can say "shared · delivered Aug 2" instead of implying it's live
};
```

Deliberately **excluded** from this shape: the brief/prompt text (may itself
contain client-confidential detail the owner didn't mean to make public just
by sharing the *output*), decision log, sources' full URLs if they'd leak
research strategy, memory/hydration data, owner identity, token/cost usage,
model choice, project name. Flagging that the brief-exclusion is a real
design call, not an oversight — if the owner wants the ask visible on the
public page too, that's a one-line change here, but the default is "share
the deliverable, not the working."

## Artifact downloads

Needs a matching unauthenticated download route, e.g.
`GET /share/{token}/artifacts/{name}` — mirroring the shape of the existing
authenticated `/runs/{id}/artifacts/{name}`. Not spelling out a full second
spec file for this since it's the same pattern with the token standing in
for auth; flag if you'd rather see it written up separately.

## Failure cases the UI needs to distinguish

| Case | Expected | Why the UI cares |
|---|---|---|
| Unknown token | 404 | renders "this link doesn't work — it may have been revoked" |
| Revoked token | 404 — **identical** to unknown | see the non-disclosure requirement in the paired create/revoke request; the public page cannot be allowed to distinguish "revoked" from "never existed" |
| Run still running when fetched | shouldn't be reachable — the create endpoint only issues a token for a terminal run (paired request) | — |

## How the frontend is coping meanwhile

Not coping — no public route exists in the frontend yet, nothing mocked.
Both this and the paired create/revoke request need to land together before
any UI work starts; there's no useful partial build of half this contract.

---

<!-- backend appends below this line; do not edit the section above -->
