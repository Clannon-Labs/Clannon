
## dispatched workers
- `15:08` **api** worker via **claude** — 2026-08-09_private-alpha-waitlist.md — exit 0, 969s — output: `.agents/runs/20260809-145213-api.out`

## Private-alpha waitlist is built; provider is Resend

Owner ruled the access gate is a **waitlist**, not an allowlist: email + optional note
→ verify inbox → owner approves individually → account created. `97dfdb7`, pushed.
Suite 1670.

### frontend — this changes your signup page, and there are new routes

`specification/api/ROUTES.md` has the shapes. Summary:

| Route | Auth | Note |
|---|---|---|
| `POST /waitlist` | no | `{email, note?}` → **202**, always the same body |
| `POST /waitlist/resend` | no | same body, same non-disclosure |
| `GET /waitlist/verify?token=` | no | redirects to `/waitlist/confirmed` or `/waitlist/invalid-link` |
| `POST /auth/signup` | no | **now requires `approvalToken`** while the gate is on |

**Three things the UI must not do:**

1. **Never tell the visitor whether an address is already on the list.** The response
   is identical for new, listed, verified, approved, and already-a-user. That is
   deliberate — otherwise the page is an account-existence oracle. Do not add a
   "you're already signed up!" state; you cannot know it and neither can the server
   tell you.
2. **Never say the email was sent.** `Accepted` from the mailer means the provider took
   it, not that it arrived. Copy should be "if that address is valid, you'll get a
   link" plus a resend affordance.
3. **`/waitlist/confirmed` and `/waitlist/invalid-link` are pages you own** — the verify
   route redirects to them and they do not exist yet.

Signup's `email` field is now ignored while the gate is on; the account's address comes
from the approval token, so a mistyped field cannot create the wrong account.

### everyone — the provider lives in exactly one file, and a test enforces it

`core/mail.py` is the only module allowed to know a provider's name.
`tests/mail_port.py` fails the suite if a provider name or SDK appears anywhere else —
verified non-vacuous by leaking `RESEND_API_KEY` into `api/waitlist.py` and watching it
go red. Reach mail through `foundation.Mailer` / `resolve_mailer()`.

Note the bare word "resend" is excluded from that pattern on purpose: it is also our own
vocabulary (`POST /waitlist/resend`), and matching it flagged nine innocent lines.

### blocked on the owner, and only this

A Resend account, `RESEND_API_KEY`, and `CLANNON_MAIL_FROM` on a domain with SPF/DKIM
records. Until then `LogMailer` runs and **refuses to start in production**, so a real
deployment cannot silently log its verification emails instead of sending them.

## Codex interactive resume fixed

`crew.sh start <role> --codex` now resumes latest interactive Codex session for that
role's exact cwd. Current Codex scopes `resume --last` by cwd; old launcher assumption
that selection was global was stale. `--fresh` still bypasses resume, and headless
worker sessions are excluded. Hermetic launcher tests cover all seven roles plus
cross-role isolation.
