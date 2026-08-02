# Cancel subscription, real downgrade, and invoice/receipt history

```
From:     frontend
To:       backend
Date:     2026-08-02
Status:   OPEN
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

Three separate concerns, likely three routes (naming is backend's call):

| | |
|---|---|
| Method | `POST` |
| Path | `/billing/cancel` |
| Auth | required |
| Body | `{ reason?: string }` — optional, for churn signal |

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
type CancelSubscriptionResponse = {
  status: "cancelled" | "scheduled"; // scheduled = takes effect at period end
  effectiveAt: string; // ISO — when access actually changes
};

type DowngradeResponse = {
  status: "applied" | "scheduled";
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

Say explicitly if "scheduled" cancellation/downgrade even makes sense for this
product's billing model (fixed-period budgets, not a metered subscription per
`billing.py`) — the UI's copy depends on whether "cancel" means "stop future renewal"
or "revoke access now," and those need different confirmation language.

## How the frontend is coping meanwhile

No UI attempts any of these three actions. `billing-settings.tsx` keeps the existing
disabled-downgrade card and the refund-policy link as-is. Nothing is stubbed against a
contract that doesn't exist yet — this is a real gap, not a coping mechanism.

---

<!-- backend appends below this line; do not edit the section above -->
