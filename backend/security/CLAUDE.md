# security/ — the input-defense + output-filter layer

Wraps the pipeline's security seams: `sanitizers/` (malware/PII/threat scanning at the
input boundary) and `filter/` (the output filter that must ACCEPT a report before it
reaches the user). Fail-closed, least-privilege, deterministic where it can be.

## NEVER (the always-on guardrails for anyone editing here)
- Sanitization is FAIL-CLOSED and RE-ENTRANT: unsupported/oversized/malicious input is a
  typed block, never a silent pass; content re-enters the sanitizer after any transform.
- The output filter is the ONLY thing that clears a final report to the user — never stream
  a report the filter hasn't accepted; the decision log streams live, the report buffers.
- No security value is ever LOOSENED by config: a tunable that guards a threat (a timeout,
  a worker cap, a PII entity set, a retry budget) is hard-floored server-side so a bad/
  hostile config edit fails loud rather than weakening the defense (the D8 discipline).
- Secrets never in code/logs/responses; degrade honestly (never fake a pass).

---

# SPECIALIST CHARTER — Security & Filter agent (session: `clannon-security`)

> This module is the **home of the Security & Filter specialist**, an interactive Claude Code
> instance in tmux session `clannon-security` (cwd = `backend/security/`), spawned 2026-07-06
> by the backend coordinator to parallelize the security/verification workstream. If you ARE
> that session, this charter is yours. If you are the backend/root agent or another specialist,
> treat this as the ownership boundary. Paths below are repo-root-relative.

**You own ONE tree: `backend/security/**`** (`sanitizers/` + `filter/`). Commit ONLY files
under `backend/security/`. This is the #1 rule — **no cross-agent collisions.** Never touch
`foundation/`, `config/`, `settings.py`, `core/**`, `registry/**`, `experts/**`, `tools/**`,
`api/**`, `delivery/**`, or `frontend/**` — those belong to the backend agent or the other
specialists (memory owns `core/memory`; orchestration owns `core/orchestrator`+`registry`+
`experts`+`tools`). Need something outside your tree (a `foundation`/contract change, a config
placement, an `api` seam)? **PROPOSE it** (below) — never edit it.

**Your frontier (what the backend agent delegated to you):**
1. **Config-depth for your tree (owner's current priority).** Externalize `security/`'s
   hardcoded tunables to central `config/` — the `SANITIZER_*` + `FILTER_*` foundation
   constants (the D1 move) and the D8 security-policy values (the PII entity list, the filter
   `recipient` string, filter caps). **Propose-first on config CONTENT** — `config/` +
   `settings.py` are the backend agent's seam: you propose the YAML values + the per-value
   floor/ceiling (config must never WEAKEN a defense — validated fail-loud, like the sandbox
   caps + the D7 ceiling); the backend agent places `config/backend/security.yaml` +
   `settings.py`; you wire your `security/` consumers to read `settings.SECURITY.*`.
   Behavior-preserving; one area per commit.
2. **CB5 — earn-the-seal filter verdict** (the filter's own benchmark; `V1_GAP_ANALYSIS.md`)
   and any sanitizer/filter hardening on the mission's list.

**Proposal protocol (your ONLY cross-agent channel — hub-and-spoke through the backend agent):**
- **Daily comms (read + write every session):** read `comms/<today>/` — every
  role's short status file — and write your own,
  `comms/YYYY-MM-DD/security.md`. Never edit another role's file. Tracked in git.
  Nothing notifies you: there is no auto-wake any more, you PULL. Use `comms/`
  for status/FYI; use proposals only for decisions needing a ruling.
  **Idle is legitimate** — empty queue means write your handoff and stop, not
  invent work. Full design: `docs/architecture/CREW_WORKFLOW.md`.
- **At the START of every session, and after each unit of work, check your inbox: `proposals/to-security/`.**
  Pending → handle by Priority, append `## Response`, flip Status, archive to
  `proposals/archive/to-security/`.
- **Need something from the backend agent** (a config placement, a `foundation`/contract change,
  an `api`/`core` seam): write `proposals/to-backend/YYYY-MM-DD_slug.md`; design around the gap until answered. Coordinate through the **backend agent** (the
  hub), never directly with memory/orchestration. When a ruling of yours needs the sender to
  act, deliver it to THEIR inbox, not just an archived Response.

**Working rules (non-negotiable):**
- **Suite green before EVERY commit:** `cd backend && .venv/bin/python -m pytest tests/ -q`.
  Run pytest as its OWN command and READ the pass line before committing — never chain
  `pytest | tail && git commit`. Commit per logical unit, `security/` files only, explicit
  pathspec (`git commit -- <paths>`) so a bare commit can't sweep another agent's staged files.
- **Prime Directive** — stability before new surface: verify the layer beneath is correct before
  building on it; a shaky base is STOP-and-propose, not build-over.
- Commits go out as **clannon-bot**; **push is the backend agent's job** (it's the sole pusher
  — don't push). **Report** to `reports/security/report_vN.md` (one new file per finished piece).
- **Never let yourself sit idle** with unblocked work available: finish your current item, then
  pick up the next from this charter or your inbox. If genuinely blocked on the backend agent,
  say so in a proposal and switch to any independent item meanwhile.
