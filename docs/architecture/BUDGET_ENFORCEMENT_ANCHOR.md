# Budget enforcement anchor — build spec `[DESIGN LOCKED, ready to build]`

The last piece of the money layer: wiring `reserve`/`reconcile` into the live LLM call path. The
**data plane is done** — `core/budget/redis_budget.py` (spend broker) + `core/budget/seed.py`
(seed/ceiling), both security-hardened. This is the **enforcement plane** on top. Build it behind
an OFF-by-default flag; it's inert (zero behavior change) until enabled.

## Placement
`core/llm/retry.py::run_agent` — the single choke point every LLM stage funnels through (security
confirmed empirically it is the *sole* `agent.run` call site). Reserve once before the retry loop,
reconcile once after.

```
reservation = await broker.reserve(scope, estimate)   # or None when unenforced/unscoped
settled = False
try:
    for attempt in range(attempts):
        try:
            result = await agent.run(...); usage.accumulate(result)
            if reservation: await broker.reconcile(reservation, actual_micros); settled = True
            return result
        except Exception:
            ...existing transient-retry / raise logic UNCHANGED...
finally:
    if reservation and not settled:
        await broker.reconcile(reservation, 0)   # any failure/exception exit → full refund
```
Reserve-once-outside-loop + `settled` + `finally` = no per-attempt leak, no double-charge
(security review §1, confirmed sound). Reconcile is idempotent, so `finally` can't double-settle.

## Security review resolutions (all accepted — see archived anchor-review)
- **#2 mission_id read LIVE per-call (the critical one).** Build `BudgetScope` at EACH reserve
  from the live current identity — `user_id` from a set-once source (authenticated api/ entry) +
  `mission_id` read LIVE (a ContextVar mirrored from `ctx.mission_id` at mission-start, never
  cached at entry). A turn that becomes a mission mid-flight must NOT carry `mission_id=""` for the
  rest of the mission — that would silently skip the mission safety cap. Coordinate the mission_id
  source with orchestration (mission-start sets the ContextVar) so it can't be stale by construction.
- **#4 loud skip when enforced-but-unscoped.** `enforcement_enabled=True` + `budget_scope is None`
  → log at ERROR (a wiring bug must be visible in prod, never silently unbilled), then skip. An
  intentional internal/CLI unscoped call uses an EXPLICIT opt-out marker (a `budget_exempt`
  ContextVar), NOT "absence of scope" — so bug vs. intentional stay distinguishable.
- **#1 partial-cost refund** — accepted as a known margin-safe tradeoff (funds only ever move the
  safe direction; a mid-call transient failure refunds fully = small margin leak, never overspend).
- **#3 no-bypass grep gate** — future `/invariant-check` addition so no new `agent.run` call site
  can skip the anchor. Nice-to-have, tracked.

## The model-rate resolution (the framework-boundary question — RESOLVED)
`run_agent(agent, ...)` is layer-agnostic, but cost needs the model's rate. The model is
layer-determined (`build_agent(layer)` → `Agent(model_for_layer(layer))`). So: a `budget_layer`
ContextVar set where the layer IS known (framework.py's `run_structured`/`build_agent` path,
mirroring `usage_scope`), read by the anchor → `rate = settings.PRICING.price_for(model_for_layer(layer))`.
- **Estimate (pre-call, worst case):** `call_cost_micros(ModelCall(model_id, input_est,
  max_output_from_usage_limits, elapsed=turn/call wall-clock ceiling))` — conservative (lean high
  so a near-empty budget can't start a large call). Input tokens unknown pre-call → a generous
  allowance; reconcile corrects to actual.
- **Reconcile (post-call, exact):** `usage.accumulate` already captures REAL provider token counts
  (`result.usage`); reconcile computes `call_cost_micros` from those + measured elapsed. Precise.

## Config (add, behind the flag)
`config/backend/budget.yaml` + `BudgetConfig` (+ `config_budget` assertions):
- `enforcement_enabled: bool` (default **false** — prod isn't seeded + prices are placeholder).
- a conservative per-call reserve buffer knob if the estimate needs one.

## Build order (each verifiable, land together so nothing is speculative)
1. Config flag (+ buffer) — `budget.yaml`/`BudgetConfig`/`config_budget`.
2. `core/budget/context.py` — ContextVars (`budget_user_id` set-once, `budget_mission_id` live,
   `budget_broker`, `budget_exempt`) + `current_budget_scope()` building the scope LIVE + set helpers.
3. `budget_layer` ContextVar wired in the framework where the layer is known.
4. `run_agent` reserve/reconcile behind the flag (#2 live scope, #4 loud skip).
5. Tests: OFF flag = byte-for-byte current behavior; ON = reserve/reconcile with a fake broker;
   the live-mission_id case (scope reflects a mission_id set AFTER entry); the loud-skip case;
   the refund-on-failure path.
6. Then: route the built code to security for the enforcement-on gate review; coordinate the
   mission_id-source wiring + go-live prices (owner) before flipping `enforcement_enabled=true`.

## Gates before enforcement-on (NOT for the build, for enabling)
- Real per-model prices + infra values set (owner decision — `pricing.yaml` is PLACEHOLDER).
- Budgets actually seeded in prod (the billing/reset trigger, Stripe deferred).
- The mission_id-source ContextVar wired at mission-start (orchestration coordination).
- Security's review of the built code.
