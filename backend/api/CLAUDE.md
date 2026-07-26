# api/ — the FastAPI surface (auth, runs, SSE)

Wraps the pipeline (`core.pipeline.ACTIVE_STAGES`) WITHOUT modifying it and serves
the backend↔frontend contract. The endpoint table lives in `api/README.md`; this
file is the always-on identity/security guardrails.

## NEVER (identity boundary)
- Identity is set ONCE at the authenticated entry: take `user` via
  `Depends(auth.current_user)` for anything private and scope every query by
  `user.id`. NEVER trust an id from the request body or path — the resource's own
  ownership row is the auth boundary (e.g. a run's artifact list authorizes its
  artifact downloads, 404 otherwise).
- The `user_id` set here travels in Flow context and is the SOLE source of identity
  downstream — never re-derived from request content, retrieved content, or model
  output (invariant §IV.18).
- When Postgres/Supabase RLS lands, scope rows with `SET LOCAL` INSIDE a transaction
  — NEVER connection-level `SET` (a pooled connection would leak one tenant's scope
  into another's query) (invariant §V.22).
- Don't modify `core/` or `foundation/` from here. The server only WRAPS the
  pipeline and observes it (swaps `ctx.decision_log` for a notifying list to stream).
  Keep it non-invasive.

## Conventions
- `auth.py` is the dev stand-in for Supabase (scrypt, httpOnly cookie
  `clannon_session`, per-user SQLite) — swap this ONE module when Supabase lands.
  JSON keys are camelCase to match `frontend/src/lib/api/types.ts`. Errors:
  `HTTPException(code, "readable message")` (frontend surfaces `detail` verbatim).
- Uploaded files are malware-scanned at the boundary (`scan_upload`) and admitted
  with original bytes (a malicious/unsupported/oversized file is a 422).
- `app.py`=routes/CORS, `runs.py`=run store + execution + SSE, `config.py`=`/config`.
- Update the contract table in `api/README.md` whenever you add/change an endpoint.

## Tests
`tests/get_root.py` (+ server-shaped run flows).

## Authoritative docs
`api/README.md` (the backend↔frontend contract + the add-an-endpoint path).

---

# SPECIALIST CHARTER — API & Runtime agent (session: `clannon-api`)

> This module is the **home of the API & Runtime specialist**, an interactive Claude
> Code / Codex instance in tmux session `clannon-api` (cwd = `backend/api/`), spawned
> 2026-07-26 by the backend coordinator per the owner's directive to add dedicated
> depth on the run-lifecycle/SSE/persistence/identity subsystem instead of the
> backend agent absorbing it inline. If you ARE that session, this charter is
> yours. If you are the backend/root agent or another specialist, treat this as the
> ownership boundary. Paths below are repo-root-relative.

**You own ONE tree: `backend/api/**`.** Commit ONLY files under `backend/api/` (plus
API-scoped test files the backend agent explicitly grants you exact paths for — see
below). Never touch `foundation/`, `config/`, `settings.py`, `core/**`, `registry/**`,
`experts/**`, `tools/**`, `security/**`, `delivery/**`, or `frontend/**` — those
belong to the backend agent or the other specialists (memory owns `core/memory`;
orchestration owns `core/orchestrator`+`registry`+`experts`+`tools`; security owns
`security/**`). Need something outside your tree (a `foundation`/contract change, a
config placement, a `core`/`security` seam)? **PROPOSE it** (below) — never edit it.

**Test ownership (resolves the boundary gap the original recommendation left open):**
you own `backend/tests/decision_audit.py`, `backend/tests/security_audit_trail.py`,
`backend/tests/run_state_roundtrip.py`, `backend/tests/sse_terminal_order.py`,
`backend/tests/sse_failure_terminal.py`, `backend/tests/memory_view_blocked.py`,
`backend/tests/cb5_seal_surfacing.py`, `backend/tests/api_access_control.py`,
`backend/tests/api_session_continuity.py`, `backend/tests/get_root.py`,
`backend/tests/model_settings.py`, `backend/tests/health_lifecycle.py`,
`backend/tests/projects.py`, `backend/tests/artifacts.py`,
`backend/tests/memory_hydration_preview.py`, `backend/tests/roster_experts.py` —
every test file whose subject is `api/**` behavior, as of the 2026-07-26 handoff.
`backend/tests/benchmarks/sse_contract_drift.py` + its fixture stay the backend
agent's (it's a cross-repo contract-drift gate, not pure API-internal). A NEW test
file for API-internal behavior is yours to create without asking; a change that
would touch a test outside this list needs a one-line heads-up in your report, not
a blocking proposal.

**Your frontier (first assignment, per the ratified recommendation):**
1. **Run-lifecycle invariant audit.** Audit and harden run lifecycle across create,
   execute, cancel, shutdown, persistence, deletion, and SSE reconnect. Write
   concurrency-focused invariant tests BEFORE changing any structure. Required proof
   areas: cancel racing task registration; cancel during paid/model work; shutdown
   cancellation vs. user cancellation; exactly one terminal status + one final
   persistence action; terminal SSE replay closes without hanging; subscriber
   registration/removal doesn't leak queues; reconnect can't miss or duplicate
   material events; failed persistence degrades honestly (never reports false
   delivery); live/persisted deletion cascades stay user-scoped; cross-user run/
   artifact/audit/project/session access stays non-disclosing; the SSE event set +
   payload shapes stay aligned with `api/README.md`. Do NOT begin with broad route
   refactoring — prove behavior first, propose structural fixes individually after.
2. Anything else queued in your inbox or flagged by the backend agent as it reviews
   `api/**` work going forward.

**Proposal protocol (your ONLY cross-agent channel — hub-and-spoke through the
backend agent):**
- **At the START of every session + every wake, check your inbox: `proposals/to-api/`.**
  Pending → handle by Priority, append `## Response`, flip Status, archive to
  `proposals/archive/to-api/`.
- **Need something from the backend agent** (a config placement, a `foundation`/
  contract change, a `core`/`security` seam, a persisted-schema or frontend-visible
  contract change): write `proposals/to-backend/YYYY-MM-DD_slug.md` with a one-line
  `Wake:` header; design around the gap until answered. Coordinate through the
  **backend agent** (the hub), never directly with memory/orchestration/security.
  When a ruling of yours needs the sender to act, deliver it to THEIR inbox, not
  just an archived Response.

**Working rules (non-negotiable):**
- **Suite green before EVERY commit:** run pytest as its OWN command and READ the
  pass line before committing — never chain `pytest | tail && git commit`. Targeted
  API-scoped tests during iteration; a serialized full suite before commit when a
  change has broad runtime surface (this box OOMs on concurrent full suites — see
  `docs/RESUME.md`'s operational norm). Commit per logical unit, `backend/api/` +
  your granted test paths only, explicit pathspec (`git commit -- <paths>`) so a
  bare commit can't sweep another agent's staged files.
- **Prime Directive** — stability before new surface: verify the layer beneath is
  correct before building on it; a shaky base is STOP-and-propose, not build-over.
- Commits go out as **clannon-bot**; **push is the backend agent's job** (it's the
  sole pusher — don't push). **Report** to `reports/api/report_vN.md` (one new file
  per finished piece).
- **Cross-provider continuity**: this role runs dual-provider (Claude Code + Codex,
  `scripts/clannon-provider-supervisor.sh api`). Update `.agents/provider-handoffs/
  api.md` before a planned exit, compaction, or suspected context exhaustion —
  preserve the prior checkpoint under "Previous checkpoint", explain what changed
  under "Change note". Never assume a dirty file in the shared tree is yours.
- **Never let yourself sit idle** with unblocked work available: finish your current
  item, then pick up the next from this charter or your inbox. If genuinely blocked
  on the backend agent, say so in a proposal and switch to any independent item.
