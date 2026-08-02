# Signup has no invite/allowlist gating — contradicts the stated private-alpha model

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   OPEN
Blocking: no            # not blocking frontend work, but this is a product-positioning
                         # gap that should reach the owner before the domain goes live
Priority: HIGH — read this before the next signup-flow change
```

## What I checked, and what it found

Root `CLAUDE.md` states this is a private alpha: *"a tester i hire can test it...
should want to use it daily... by asking me to allow them (cuz it would be private
alpha then)."* That's a stated product decision — access is meant to be owner-gated.

Read `backend/api/app.py:193-198` (`POST /auth/signup`) and
`backend/api/auth.py:177-190` (`create_user`). There is no invite code, email
allowlist, domain restriction, or approval step anywhere in the signup path — only
a password-length check, a rate limit (`_auth_rate_limit`), and a duplicate-email
409. **Anyone who can reach the endpoint can create a full account today.**
Confirmed by reading the actual handler, not inferred from the frontend (which
also has zero invite-code UI — `src/app/(auth)/signup/page.tsx` is a plain
open form, "Free plan, no card").

This is not a frontend gap to route around. A client-side invite-code field on an
ungated endpoint is exactly the kind of theater the memory-plan-tier-bypass finding
(`proposals/archive/to-backend/2026-08-01_memory-plan-tier-not-enforced-serverside.md`)
already proved doesn't hold: anything not enforced server-side isn't enforced.
Flagging now, before the domain goes live, rather than after.

## The decision this needs (yours, or the owner's — not mine)

Three genuinely different contracts, and I don't have a preference — whoever
decides should pick based on how the owner actually wants to run the alpha:

1. **Invite-code-on-signup** — `POST /auth/signup` requires a `code` field;
   codes are single-use or capped, generated/revoked by the owner somehow (admin
   endpoint? seeded list? out of scope for me to design).
2. **Email allowlist** — signup checks the email against a list the owner
   maintains (env var, config table, whatever fits `config/`); anyone not on it
   gets a clear "not open yet" message, not a confusing generic failure.
3. **Open signup, admin-approval-gated login** — account creates fine, but
   can't actually *use* the product (or gets a reduced/blocked plan) until the
   owner flips a flag. Closest to "ask me to allow them" read literally.

## What UI this would unblock

Whichever shape lands, the signup page needs to reflect it honestly — an
invite-code field, an allowlist rejection message, or a "request access, we'll
email you" pending state instead of the current "Free plan, no card" open
self-serve framing. Not building any of this yet; it depends entirely on which
of the three above gets picked.

## How the frontend is coping meanwhile

Not coping — this doesn't block any current frontend work, since signup already
functions end-to-end for testing purposes. Flagging so it's a considered decision
before the domain goes live, not something the owner discovers by using the
product themselves after the fact.

---

<!-- backend appends below this line; do not edit the section above -->
