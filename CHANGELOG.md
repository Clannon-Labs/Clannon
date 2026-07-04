# Changelog

All notable changes to Clannon. Versions follow [SemVer](https://semver.org)
(pre-1.0: minor = features, patch = fixes).

## [v0.2.0] — 2026-07-04

278 commits since v0.1.0 (64 features, 32 fixes). Tag: `v0.2.0` @ `89b3ed4`.

### Memory
- **Sole-broker context path** (ARCHITECTURE.md §7.3, now `[BUILT]`): experts
  are stateless — the turn's hydrated memory is PUSHED into non-NETWORK
  experts' tasks; the orchestrator brokers sub-task recall pre-spawn; a
  `need_context` tool gives non-NETWORK experts brokered mid-task recall
  (code-only curation: Manager ranking, cap, dedup vs the push). No expert
  holds a `memory.*` grant — locked by a registry-wide invariant test.
- **Memory-write timing**: episodic writes + distillation fire post-filter /
  post-delivery only — a draft the output filter blocks never seeds memory,
  and blocked turns surface zero phantom writes in the API.
- **`GET /memory/hydration-preview`**: read-only dry-run of the Manager's real
  trust+similarity+recency ranking for a draft brief (the workspace panel's
  "memory surfacing as you type" is now truthful).
- **Degrade-never-raise hardened**: a tier search that faults mid-gather
  degrades that tier (all-tiers fault ⇒ honest degraded package), never
  propagates out of `hydrate()`.

### Security
- Intake rate limit keys on **user_id** — rotating session ids can no longer
  bypass the per-identity window.
- Normalizer judges media capability against the **media route's** model
  (gemini multimodal), not the orchestrator's — media uploads are no longer
  mis-flagged by a text-only orchestrator profile.
- **npm audit 7 → 0** (1 critical): vitest 4 / plugin-react 5 chain (esbuild
  dev-server CORS and the vite tree), postcss `</style>` XSS bundled inside
  Next fixed via `overrides` + next 16.2.10.
- NETWORK-capable experts are excluded from the memory push and the
  need-context channel (user memory + an outbound channel in one prompt is a
  prompt-injection exfiltration surface).
- `scripts/check_invariants.py` + baseline-guard tests: grep-audit of the
  import/scope invariants (memory single-door, provider confinement, SSRF
  gate, foundation dep direction) until the CI gate lands.

### API & ops
- `/health` (liveness), `/ready` (per-dependency readiness), FastAPI lifespan
  with bounded warmup and in-flight run drain.
- Fail-fast startup config validator (strict in production env, inert in dev).
- `chart.render` tool: deterministic stdlib SVG charts.
- Benchmarks: C1/C3/C4/C5/E1 acceptance harnesses + `run_all.py` scoreboard.

### Test infrastructure
- ~50 hermetic harnesses merged across intake, sanitizers, verifier,
  normalizer media dispatch, LLM provider failover, memory write policy /
  isolation / ranking / faults, orchestrator turn budget, API access control
  (BOLA/IDOR), session continuity, SSE failure, RunState events, prompt
  overlay precedence, registry contracts.
- Shared `tests/conftest.py` isolating process-global rate limiters (auth +
  intake) between tests. Backend suite: **786 passed**.

### Agent mesh (development workflow)
- Cross-agent **proposal protocol**: the backend and frontend Claude sessions
  exchange work through `proposals/` inboxes with a defined file format —
  no owner relay (root `CLAUDE.md` §PROPOSAL PROTOCOL).
- **Auto-wake**: systemd --user path units watch the inboxes and type an
  `[auto-wake]` message into the target agent's tmux session
  (`scripts/proposal-wake.sh`, `scripts/agent-session.sh`).

### Frontend
- Premium design pass ("Botanical Archive" system, `frontend/DESIGN_SYSTEM.md`
  canon): typography/theme/motion/a11y overhaul, settled run-log history,
  staged hydration recap, workspace error/loading boundaries.
- First vitest harness (70 tests) for demo-critical surfaces.

### Docs
- Single authoritative, build-state-tagged `docs/ARCHITECTURE.md` — every
  claim `[BUILT]`/`[PARTIAL]`/`[PROPOSED]` with `file:line` citations; the two
  conflicting surface docs archived; detailed canon reconciled (embeddings =
  local fastembed ONNX, graph fork resolved → Kuzu `[PROPOSED]`, entropy
  routing honestly `[PROPOSED]`).

## [v0.1.0] — 2026-06-11

Initial architecture: the full pipeline came together (intake → sanitizers →
normalizer → verifier → orchestrator → experts/tools → output filter →
delivery), interactive TUI, first release notes.
