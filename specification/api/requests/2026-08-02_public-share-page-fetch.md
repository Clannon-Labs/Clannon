# Fetch a shared run's public-safe payload (unauthenticated)

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   QUEUED
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

## Response — 2026-08-09 (backend)

**Accepted in principle, queued behind billing, and deliberately handled as a pair.**
A share link and the unauthenticated fetch that consumes it are one feature; building
either alone produces a half-surface.

**Why it is not first, and it is not the effort.** This is the only thing in the current
queue that adds an **unauthenticated route returning user content**. Every other route
we have is owner-scoped by construction; this one is scoped by a token instead, which
means the whole non-disclosure model has to be re-derived rather than inherited. The
questions I will not answer casually:

- what a share token is, and that it is unguessable and revocable for real, not by
  hiding a row;
- exactly which fields a public payload carries — a run holds a brief, a decision log,
  sources, artifacts and memory provenance, and **most of that must never leave the
  account**;
- whether a revoked or expired link is distinguishable from one that never existed
  (it must not be);
- whether sharing survives a `revise`, which destroys turns by design.

That gets a `security-review` pass before any code, because getting it wrong leaks a
customer's work to the open internet, and unlike a bug in an authenticated route it
leaks it to people who were never users.

**Not blocked on you, and nothing to change.** Both requests are marked `Blocking: no`
and you have coped correctly. I will come back with a concrete payload shape — probably
narrower than you proposed, because the default for a public surface should be
"nothing, then add what is justified."

Status: QUEUED — after billing, security-reviewed before implementation.
