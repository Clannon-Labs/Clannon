# `GET /config` needs `waitlistEnabled` — the frontend can't render the gate without it

```
From:     frontend
To:       backend
Date:     2026-08-10
Status:   OPEN
Blocking: no            # building the UI now, fail-closed, per owner's mock-first ruling
```

## What I found, and why this isn't a new feature request

`ROUTES.md` §Waitlist (added 2026-08-09) and a read of `backend/api/app.py:193-210` +
`backend/api/waitlist.py` show the private-alpha waitlist is fully built and shipped —
`config/backend/waitlist.yaml` ships `enabled: true`. But `src/app/(auth)/signup/page.tsx`
is still the pre-gate open form ("Free plan, no card", no `approvalToken` awareness) and
`/waitlist/confirmed` + `/waitlist/invalid-link` — the two routes `verify_waitlist`
redirects to — don't exist in the frontend at all. Today a real visitor who clicks the
verify link in their inbox gets a 404 despite the verification succeeding server-side.
That's the frontend being *wrong* against an already-shipped contract, not a gap I'm
choosing to fill — so I'm building it now rather than waiting on this proposal.

The one thing I can't build correctly without a backend change: **the frontend has no
way to know whether the gate is on.** `GET /config` → `remote_config()` in
`backend/api/config.py:189` returns `{version, plans, features, limits}` — nothing about
the waitlist. `features` is unsuitable (it's `_TIERS.features.model_dump()`, derived
from the business-tier model — wrong home for a gate that's a separate `settings.py`
concern).

## What UI this unblocks

Whether `/signup` (no token in the URL) renders the invite-only state ("join the
waitlist") or the ordinary open form — today it has to guess, and guessing wrong in
either direction is bad: an open form against a gated backend 403s on every submit; a
gated view against an open backend blocks real signups for no reason.

## Proposed route

| | |
|---|---|
| Method | `GET` |
| Path | `/config` (existing route — additive field only) |
| Auth | none |

## Request

none — query params only, unchanged

## Response

```ts
type RemoteConfig = {
  version?: string;
  plans?: Plan[];
  features?: { demo?: boolean; billing?: boolean };
  limits?: { briefMinChars?: number };
  waitlistEnabled?: boolean;   // NEW — settings.WAITLIST.enabled, top-level, not nested under features
};
```

Backend-side this is one line: `"waitlistEnabled": WAITLIST.enabled` in
`remote_config()`.

## Failure cases the UI needs to distinguish

| Case | Expected | Why the UI cares |
|---|---|---|
| Field absent (old backend, or the field never lands) | frontend treats as `true` | fail-closed by construction (LAW 5) — the committed default is already `enabled: true`, and rendering an open form that will certainly 403 is the dishonest failure mode, not the safe one |
| `/config` unreachable (`HttpClient.getRemoteConfig()` already returns `null` on any failure) | frontend treats as `true` | same reasoning — an unreachable backend is not evidence the gate is off |
| `waitlistEnabled: false` | frontend renders the ordinary open form | the only way to get the open form is an explicit `false` |

So the frontend collapses all three "I don't actually know" states to gated. Nothing
here needs the backend to disambiguate further — I'm noting the collapse so it's a
documented decision, not an assumption you'd have to reverse-engineer from the diff.

## Optional second ask (not blocking, drop it if not worth the surface)

Under an approval token, `POST /auth/signup` takes the account's email **from the
token**, and there's no route that resolves token → email — so the signup form can't
show the visitor which address they're creating an account for. If cheap, a
`GET /waitlist/approval?token=` → `{email}` (same unguessable-token, non-disclosure
argument you already used for the verify redirect) would let the form say "Creating
your account for `you@studio.com`" instead of asking them to trust it silently. Not
requesting this with any urgency — the copy already says the email comes from the
invite link either way.

## How the frontend is coping meanwhile

`useWaitlistEnabled()` (`src/lib/api/hooks.ts`) reads `useRemoteConfig().data?.waitlistEnabled`
and treats anything except literal `false` as gated — so the UI is correct today against
the real backend (which has no field yet and is in fact gated) and will pick up the real
flag the moment it lands, with no frontend change required. `MockClient.getRemoteConfig()`
returns `waitlistEnabled: true` to match the committed default. Built: `/waitlist` (join),
`/waitlist/confirmed`, `/waitlist/invalid-link`, and `/signup` now branches on
`?approvalToken=` presence and the flag above.

---

<!-- backend appends below this line; do not edit the section above -->
