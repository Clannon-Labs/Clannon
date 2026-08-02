# Create and revoke a public read-only share link for a run

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   OPEN
Blocking: no            # not built into frontend UI this session — see context below
```

## Context — why this is a proposal, not a build

Owner asked frontend to find a genuine premium-vs-normal UX differentiator
and build it. Survey + `benchmark/PAID_PRODUCT_BENCHMARK.md`'s Gate 90
("Delivered work supports review, source inspection, correction, refinement,
**sharing**, and export") turned up sharing as real and unbuilt — no
`share`/`public link` anywhere in the frontend, confirmed by grep and by
`REAL_JOURNEY.md`'s own limits list.

Deliberately **not building the UI or a public route this session**: Clannon
is a private alpha where the owner personally gates every account, and a
run's brief is often a named client's confidential business context (the
seed data literally is — "Meridian Skincare," a named DTC brand). A one-click
"anyone with this link can view" control is real new attack surface on
exactly the kind of data the owner's stated bar ("a tester should not find
any vulnerabilities") is about. Filing the shape now so it's a considered
decision backend can prioritize or push back on — not shipping it unreviewed
in the same session it was thought of.

## What UI this unblocks

A "Share" control next to the existing Copy/Download icons in a delivered
run's report header (`src/app/app/runs/[id]/page.tsx`, same row as
`copyReport`/`downloadReport`). Opens a small popover: no link yet → "Create
a shareable link" with an explicit explanation of what becomes visible;
link exists → the URL, a copy button, and "Revoke."

## Proposed routes

| | |
|---|---|
| Method | `POST` |
| Path | `/runs/{id}/share` |
| Auth | required (owner only) |
| Body | none |
| Response | `{ "token": "...", "url": "https://.../share/{token}" }` — 201, or 200 if a link already exists (idempotent, does not rotate the token) |

| | |
|---|---|
| Method | `DELETE` |
| Path | `/runs/{id}/share` |
| Auth | required (owner only) |
| Response | 204. Idempotent — revoking an already-unshared run is a no-op, not an error. |

## Security requirements (non-negotiable, not just a preference)

- **Token must be unguessable** — a real random token (e.g. 128-bit, url-safe),
  never the run's own id or anything sequential/derivable. The run id is
  already exposed in the frontend's own URLs; the share token is the only
  thing standing between "opt-in public" and "de facto public."
- **Explicit opt-in per run.** No run is ever shareable by default; the
  token only exists after this endpoint is called once.
- **Revocation must actually invalidate** — `GET /share/{token}` on a
  revoked token must 404, not soft-fail with a "this link is off" page (an
  attacker who captured the token before revocation should not still be
  able to distinguish "revoked" from "never existed," consistent with the
  non-disclosure rule in `ROUTES.md` §0, applied here even though this
  route has no user-ownership check to hide behind).
- **One token per run, not per share-click** — repeated `POST` returns the
  same token so "Share" isn't a rotate-and-invalidate-old-links button by
  accident.

## Failure cases the UI needs to distinguish

| Case | Expected | Why the UI cares |
|---|---|---|
| Run not owned by caller | 404 | non-disclosure, same as every other run route |
| Run not yet terminal (still running) | 409 or 422 — your call | sharing a live/in-progress run is a separate, harder design question (does the public page also stream?); frontend's plan is to only show the Share control once `isTerminal`, so a race is the only way this is reached |
| Already shared | 200 with the existing token | not an error — see idempotency above |
| Already revoked, revoke again | 204 | idempotent |

Say explicitly if there's a cheaper shape — e.g. folding `shareToken`/
`shareUrl` directly onto `GET /runs/{id}`'s response instead of a dedicated
endpoint, if that's simpler on your side. Frontend has no preference between
the two shapes, only that create/revoke are both explicit, owner-authed
actions.

## How the frontend is coping meanwhile

Not coping — genuinely not building the Share control until this exists.
Nothing is mocked or stubbed for it.

---

<!-- backend appends below this line; do not edit the section above -->
