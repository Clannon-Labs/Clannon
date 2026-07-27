# backend/ — backend agent pointer

The backend agent's full instructions live in the ROOT `CLAUDE.md` (role,
operating model, and the **Proposal Protocol**). Module-specific guardrails live
in each module's own `CLAUDE.md` (foundation/, core/*, security/*, registry/,
experts/, tools/, api/, delivery/).

## Your channels — check at session start AND after each unit of work

Nothing notifies you. **You pull** — the auto-wake and idle heartbeat are gone
(`docs/architecture/CREW_WORKFLOW.md`, canonical).

- `../comms/<today>/` — every role's short daily status. Read all of them; write
  only your own (`../comms/YYYY-MM-DD/backend.md`). Tracked in git.
- `../proposals/to-backend/` — decisions needing YOUR ruling, from the frontend
  agent AND all four specialists (memory, orchestration, security, api).
- `./proposals/` — proposals from the OWNER to you.

Pending items: announce in one line ("N pending proposals: <slugs>"), then
handle per the root protocol. To ask another side for something, write
`../proposals/to-<role>/YYYY-MM-DD_slug.md` — never edit their tree, never route
through the owner. Format: `../proposals/README.md`.

**Idle is legitimate.** Empty queue → write your handoff and stop; don't invent
work. And per root `CLAUDE.md`, challenge an instruction that would harm the
team *before* acting on it.
