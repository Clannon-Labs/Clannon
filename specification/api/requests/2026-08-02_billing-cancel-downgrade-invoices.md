# Cancel subscription, real downgrade, and invoice/receipt history

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   QUEUED
Blocking: no
```

## What UI this unblocks

Today a paying user who wants to cancel, downgrade, or just see what they were
actually charged has no path to any of it inside the product. `billing-settings.tsx`
explicitly disables downgrade in the UI ("Downgrades are not available through mock
checkout", `src/components/app/billing-settings.tsx:184`), there is no cancel action
anywhere, and the "Checkout status" list (`billing-settings.tsx:194-218`) is a log of
checkout *events* — not an invoice or receipt history. The only cancellation path is a
static link to `/legal/refunds`. For a paid product this is a normal, expected self-
serve action; right now it requires emailing someone.

Read `useBillingPortal` (`src/lib/api/hooks.ts:306-317`), `openBillingPortal`
(`src/lib/api/http.ts:498-500`, `src/lib/api/mock.ts:768-778`), and the real handler
(`backend/api/billing.py:477-490`) before building against this — all three already
return a literal `mode: "mock"` and are honestly typed/commented as such
(`BillingPortalInfo`, `src/lib/api/types.ts:393-399`: *"There is no real Stripe portal
yet (private alpha)"*). So this isn't a hidden gap, it's a documented one — but it's
real, and it's the shape of gap a hired alpha tester would hit on day one of trying to
leave.

## Proposed route

**Update 2026-08-02 (frontend, same day):** built the full UI against this
contract in mock mode rather than waiting (owner: file the contract, ship the
frontend now, the real route lands when it lands). That forced a real answer
to the "does scheduled cancellation even make sense" question below —
recorded here, not left open, but still backend's call to confirm or
override:

- **Cancel is always scheduled**, never immediate. Access continues through
  `cancelEffectiveAt` (the current period's end). This product bills fixed
  monthly budgets, not metered usage, so there's no partial-period proration
  question to solve either way.
- **Downgrade is always immediate**, and only offered between paid tiers.
  Free is deliberately NOT a downgrade target — that's what Cancel does, on
  its own schedule. One path to "end up on Free," not two with different
  timing semantics competing in the same UI. Blocked (409) if current usage
  already exceeds the target's budget — mock does not implement a "scheduled
  downgrade for next period" fallback; that's a real design question if
  backend wants it (see the failure-case table).

Four routes now (a fourth added — undo didn't exist in the first draft, and a
scheduled action needs one):

| | |
|---|---|
| Method | `POST` |
| Path | `/billing/cancel` |
| Auth | required |
| Body | `{ reason?: string }` — optional, for churn signal |

| | |
|---|---|
| Method | `POST` |
| Path | `/billing/cancel/undo` |
| Auth | required |
| Body | none |

| | |
|---|---|
| Method | `POST` |
| Path | `/billing/downgrade` |
| Auth | required |
| Body | `{ targetPlanId: PlanId }` |

| | |
|---|---|
| Method | `GET` |
| Path | `/billing/invoices` |
| Auth | required |
| Query params | none — always the caller's own account |

## Request

```ts
// cancel
type CancelSubscriptionRequest = { reason?: string };

// downgrade
type DowngradeRequest = { targetPlanId: string };
```

## Response

```ts
// always "scheduled" per the decision above — "cancelled" dropped from the
// union since the mock never produces it and the UI has nothing to render
// for an immediate-revoke state
type CancelSubscriptionResponse = {
  status: "cancel_scheduled";
  cancelEffectiveAt: string; // ISO — ALWAYS the current period's end
};

// POST /billing/cancel/undo response: same shape, status: "active" +
// cancelEffectiveAt: null

// always "applied" — no "scheduled" downgrade path implemented, see above
type DowngradeResponse = {
  status: "applied";
  effectiveAt: string;
  newPlanId: string;
};

type Invoice = {
  id: string;
  issuedAt: string; // ISO
  amountCents: number;
  currency: string;
  status: "paid" | "open" | "void" | "refunded";
  description: string; // e.g. "Pro plan — August 2026"
  downloadUrl?: string; // PDF, if backend can produce one
};
type InvoicesResponse = { invoices: Invoice[] };
```

## Failure cases the UI needs to distinguish

| Case | Expected | Why the UI cares |
|---|---|---|
| Downgrade below current usage this period | 409 + reason | UI should explain *why* it's blocked, not show a generic error |
| Cancel on an already-cancelled/scheduled account | 409 | avoid a confusing double-cancel state |
| No invoices yet (brand-new account) | `{ invoices: [] }` + 200 | renders "nothing billed yet", not an error |
| Not authenticated | 401 | existing session-expiry handling covers this |

## How the frontend is coping meanwhile

**No longer coping — built.** `billing-settings.tsx` has real cancel/undo/downgrade/
invoices UI, fully wired and working against `MockClient`. `HttpClient` calls the
exact routes/payloads above and will work unmodified once backend builds them (three
tests in `src/tests/billing-client.test.ts` pin the exact request shape so drift gets
caught). `POST /billing/mock/confirm`-style server-only endpoints were not needed here
— unlike checkout, these three don't have an async settlement step in the mock's
design (open question below for whether the real backend needs one).

**Open question for backend**: should downgrade or cancel actually need async
settlement (pending → confirmed, like checkout does), or can they resolve
synchronously? The mock made them synchronous because there's no real payment
processor to round-trip with yet, but a real Stripe-backed cancel/downgrade might
genuinely need to wait on a webhook. If so, the response shapes above need a
`"pending"` status added and the frontend needs to poll it — flag back here if that's
the case rather than assuming synchronous.

---

<!-- backend appends below this line; do not edit the section above -->

## Response — 2026-08-09 (backend)

**Accepted, and this is the one I am building first.** Reasons, so the ordering is not
arbitrary: the UI already exists against your mock, every route is authenticated and
owner-scoped so it opens no new attack surface, and "a paying user cannot leave without
emailing someone" is the single most embarrassing gap for a hired alpha tester.

**Your two design calls are confirmed, not overridden:**

- **Cancel is scheduled, never immediate**, with access through `cancelEffectiveAt`.
  Correct, and your reason is the right one — fixed monthly budgets mean there is no
  proration question either way, so immediate cancellation would just destroy value the
  user already paid for.
- **Downgrade is immediate and paid-tier-only, Free reached only via Cancel.** Also
  correct. Two paths to the same end state with different timing semantics is how a
  billing UI starts lying about what will happen.

**On the 409 when usage already exceeds the target budget:** keeping your behaviour, not
adding a scheduled-downgrade fallback. A downgrade that silently takes effect next
period is a promise the user cannot see, and we have no surface that would show it
pending. A clear refusal that says *why* is more honest than a deferred action.

**One thing I will not carry over from mock, and you should know before wiring:**
`POST /billing/mock/confirm` is unauthenticated and dev-only. The real cancel/downgrade
routes are authenticated and owner-scoped, and settlement will not be reachable the way
mock's is. If any of your UI depends on the mock confirm path being callable, that is
the part that will need changing.

Route table and exact response shapes land in `ROUTES.md` when the code does — not
before, per this directory's own rule. I will post the shapes in `comms/` as soon as
they are real so you can move `http.ts` off the mock.

Status: IN PROGRESS — building now.

## Status correction — 2026-08-10 (backend)

Waitlist work preempted this request and shipped first. Re-checked backend routes:
cancel/downgrade/invoices remain absent, so "building now" is no longer honest.
Contract decisions above remain accepted. Status: QUEUED — next API-owned slice;
no frontend change needed meanwhile.
