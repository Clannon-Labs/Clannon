# THE CODING LAWS — Clannon backend (non-negotiable)

> **These are LAWS, not principles.** Every agent (backend/root, memory, orchestration,
> frontend) and every session obeys them, and prioritizes them relentlessly over
> convenience. Every change is checked against all five before it lands. A violation you
> find is FIXED or explicitly FLAGGED — never left. Owner-authored 2026-07-05.
>
> Enforcement lives in the always-loaded `CLAUDE.md` (root + per-module) which points here;
> this file is the full, authoritative text. If a law and a "quick way" conflict, the law wins.

---

## LAW 1 — MODULARITY (zero redundancy, one clean home for everything)

- **No redundant code anywhere.** Single source of truth. If two places do the same thing,
  consolidate to ONE and have the other call it. A copy-pasted block is a bug.
- **One function = one job.** If a function does two things, split it.
- **One file = one KIND of job.** A file holds one coherent responsibility (one type, one
  concern), not a grab-bag.
- **One folder = one layer** (memory, registry, verifier, orchestrator, security, api,
  delivery, …) — or that layer's collection of utility files/functions. Nothing lives in
  the wrong layer.
- A new thing goes in its correct existing home; you do NOT create a parallel or duplicate
  path because it's faster right now.

## LAW 2 — MAINTAINABILITY / READABILITY (a developer must LOVE reading it)

- Any developer opening the code finds it **intuitive** — the *why* is explained (docstrings
  + comments that teach, not restate), naming is precise, structure is obvious.
- **No long files.** Hard cap **500 lines**, and only reach it when cutting below would
  genuinely hurt clarity; otherwise keep files well under it (~300). A file growing past this
  is a signal to split by responsibility.
- **No long functions.** A function stays short + single-purpose; extract helpers before it
  sprawls.
- Match the surrounding code's idiom, comment density, and conventions — the codebase reads
  as if one careful author wrote it.

## LAW 3 — SPEED, and FLOW/FOUNDATION IS THE SPINE

- The code is **blazingly fast** — no wasted work, no redundant passes, bounded everything.
- **`foundation/` + `Flow` is the SPINE** (the circulatory / respiratory system of the
  backend), NOT just a feature. **If `Flow`/`foundation` can carry or do something, it MUST —
  nothing else takes `Flow`'s job.** Cross-stage transport, context, shared contracts,
  vocabulary: all ride the spine; no side-channels.
- **THE PIPELINE RUNS FROM EXACTLY ONE PLACE:** `core/pipeline.py` is the ONLY module that
  executes the stage chain. Every entry point (API, CLI, tooling, tests-that-drive-a-turn)
  calls `pipeline.run()` — **nothing else re-walks or re-implements the stages.** If you see
  a second place stepping the pipeline, that is a LAW-3 violation to consolidate. (One driver
  = speed + maintainability + security together: one place to optimize, one place to secure.)

## LAW 4 — SECURITY / PRIVACY (backend governs; config is single-source + private)

- **Single config source per concern.** Each changeable-value kind has exactly ONE config
  file (models → `models.yaml`; and so on). **No configuration logic lives outside its config
  file** — to change anything, the owner edits ONE place. All config sits together in ONE
  shared, well-chosen folder — never scattered.
- **Config is private.** Config files are the owner's; no code path (especially `api/`)
  exposes their contents or lets anything outside the owner's own channel read or change them.
- **The backend GOVERNS the frontend.** The frontend only DISPLAYS what the backend gives it,
  and can only change what the backend has EXPLICITLY exposed for a normal user — harmless,
  use-case-natural things (their own default model, deleting their own memory, a setting we
  surfaced). **Everything else is immutable from the frontend — structurally, server-side,
  not by trusting the frontend.** If the frontend is bypassed, tampered with, or hacked, it
  gains NO privilege: the backend re-checks identity + authorization + validity on every
  request and refuses anything not in the exposed-for-users set. `api/` is the most
  attack-exposed surface — scrutinize it hardest; never trust a value from the request body,
  path, or a client for anything security-bearing.

## LAW 5 — PRODUCTION-GRADE BY DEFAULT (do what real systems do, even unlisted)

If a real production-grade system does something not spelled out above, do it too:
fail-closed on faults; least-privilege everywhere; identity set once from a trusted source;
bounded resources (timeouts, hop/loop caps, size caps); idempotency where it matters;
observability without leaking internals; **no secrets in code, logs, or client responses**;
degrade honestly (never fake success); and a test that proves the behavior, not just the
happy path.

---

## How the laws are enforced

- **Always-loaded:** root `CLAUDE.md` §CODING LAWS points here; every module `CLAUDE.md` and
  every specialist charter carries the pointer, so no agent works without them in view.
- **Per change:** before committing, self-check against all five (esp. file length, single
  config home, one pipeline driver, frontend-can't-escalate).
- **Compliance pass:** the codebase is audited against these laws and violations fixed
  (tracked in the owner's `/LAW/` report). New code must not add violations.
</content>
