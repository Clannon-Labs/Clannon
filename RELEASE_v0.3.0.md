# v0.3.0 — verified answers, code intelligence, and an honest runtime

Clannon v0.3.0 makes verification visible, gives coding workflows a persistent
repository workspace, turns memory into a connected knowledge web, and closes
several runtime paths that could previously report success or cancellation
before durable state agreed.

## Highlights

### Verification users can see

Delivered runs now carry groundedness through output filtering, persistence,
REST, SSE, and frontend rendering. The verification seal shows one of four real
states: `grounded`, `partial`, `ungrounded`, or `not_applicable`.

The seal renders only from a persisted terminal run. A verdict that never
reaches durable storage cannot paint a badge.

### Code intelligence for real repositories

- Safe zip-repository upload and extraction into an expert workspace.
- AST-aware symbol search and dependency-graph traversal.
- Precise edits through `fs.patch` and line-ranged `fs.read`.
- Workspace continuity across calls within one mission.
- Automatic symbol-level graph indexing.

### Memory becomes a knowledge web

Memory can represent entities, facts, claims, and media segments as connected
graph records. A contradiction judge adds `CONTRADICTS` relationships when
claims about shared entities conflict.

### Durable institutional decisions

Run decisions are persisted and available from `GET /runs/:id/decisions`.
Cancelled and crashed runs now retain decision records too, instead of losing
their audit trail.

### Autonomous missions and first batch tier

Mission Engine now participates in the orchestrator loop. This release also
introduces the first concrete batch tier for engineering workflows.

### Central owner control panel

Business tunables now live under central `config/` with typed, fail-loud
loading. Plans, limits, model selection, budget controls, and security ceilings
have one authoritative home.

## Security and reliability

- **Runaway model-call guard owned by Clannon.** A pydantic-ai upgrade changed
  loop-limit behavior and allowed 64 calls against a bound of 22. Clannon now
  pins the proven dependency version and enforces an independent request
  counter before provider calls. Library enforcement remains defence in depth.
- **Durability before delivery.** Terminal state is persisted before SSE reports
  delivery. Persistence failure produces an honest failure instead of a phantom
  success.
- **Cancellation race closed.** Cancellation can no longer report success while
  the run continues spending and later overwrites itself as delivered.
- **Archive uploads hardened.** Zip-bomb limits, zip-slip rejection, symlink
  rejection, per-member malware scanning, and centrally configured ceilings.
- **Batch privileges fail closed.** Batch definitions cannot request NETWORK or
  ELEVATED grants.
- **Budget paths hardened.** Negative estimates are rejected and Redis budget
  key namespaces are disjoint.
- **Frontend dependency exposure reduced.** Dependabot alerts fell from 15 to 1.

## API compatibility

No breaking API changes are declared in this release.

Additive surfaces:

- `verificationState` on delivered runs.
- Typed `verification` SSE frame.
- `GET /runs/:id/decisions`.

Clients that ignore unknown response fields and SSE event types remain
compatible.

Operator note: `pydantic-ai` is pinned to `2.4.0`. Do not unpin it without
re-proving request and loop bounds.

## Known limitations

- Budget enforcement ships off by default. Pricing configuration still contains
  placeholders; real per-model prices are required before enabling it.
- V1 capability work remains incomplete. CB3 and EB3 remain open; batch
  architecture beyond the first engineering tier is parked pending design.
- CB5 adversarial detection remains partial for one recorded payload.
- Concurrent `code.engineer` calls in one mission can race on the shared
  workspace snapshot; last write wins.
- Crash-path decision records cannot recover expert/tool participants when no
  final Flow exists, so those records retain the decision without attribution.
- One high-severity Dependabot alert remains in a dev-only ESLint dependency
  chain, with no runtime exposure and no upstream fix.
- Thirteen Qdrant/ClamAV-dependent tests skip when those services are absent.

## Verification

- GitHub CI green at `25ab70d` (`30284614930`).
- Backend: 1,489 passed, 13 environment-dependent skips.
- Frontend lint and production build: passed.
