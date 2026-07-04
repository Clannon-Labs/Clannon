# Release: v0.2.0 — memory sole-broker, agent mesh, security hardening

> Publish under tag **`v0.2.0`** (already pushed, points at `89b3ed4`).
> Suggested title: `v0.2.0 — memory sole-broker, agent mesh, security hardening`
> Release body = everything below the line. This file is a paste-buffer —
> delete it after publishing; `CHANGELOG.md` is the durable record.

---

278 commits since v0.1.0 — 64 features, 32 fixes. Highlights:

### 🧠 Memory becomes sole-broker
Experts are now **stateless**: the Memory Manager hydrates once per turn, the
context is *pushed* into each (non-NETWORK) expert's task, the orchestrator
brokers sub-task recall before spawning, and a `need_context` channel covers
mid-task discovery — no expert holds a memory grant (enforced by a
registry-wide invariant test). Memory writes moved **post-filter /
post-delivery**: a draft the output filter blocks never seeds memory. New
`GET /memory/hydration-preview` gives the UI the Manager's *real* ranking for
a draft brief. Mid-flight store faults degrade honestly instead of raising.

### 🔒 Security hardening
- Rate limiting keys on **user_id** — session-id rotation no longer resets a
  caller's budget.
- Media capability is judged against the **media route's** multimodal model,
  not the text-only orchestrator profile.
- **npm audit: 7 → 0** (incl. 1 critical in the vitest chain; postcss XSS
  bundled inside Next fixed via override + next 16.2.10).
- NETWORK-capable experts are walled off from pushed memory and mid-task
  recall (prompt-injection exfiltration surface, closed).
- New `check_invariants.py` grep-gate audits the import/scope invariants.

### ⚙️ API & ops
`/health` + `/ready` + graceful lifespan (bounded warmup, run drain),
fail-fast startup config validation, an SVG chart tool, and the C1–E1
benchmark harnesses with a `run_all.py` scoreboard.

### 🧪 Tests
~50 hermetic harnesses merged across every pipeline stage and the API
surface; process-global rate limiters isolated between tests.
Backend suite: **786 passed**.

### 🤝 Agent mesh (dev workflow)
The two interactive agent sessions exchange work through a `proposals/` file
protocol with **auto-wake** (systemd path units → tmux send-keys) — no human
relay between them.

### 🎨 Frontend
"Botanical Archive" premium design pass (type, theme, motion, a11y), settled
run-log history, staged hydration recap, route-segment error/loading
boundaries, and a first 70-test vitest harness.

### 📚 Docs
One authoritative, build-state-tagged `docs/ARCHITECTURE.md` — every claim
tagged `[BUILT]`/`[PARTIAL]`/`[PROPOSED]` and cited to `file:line`; honest
about what is aspiration vs. running code.

**Full changelog**: `CHANGELOG.md` (or `git log v0.1.0..v0.2.0`).
