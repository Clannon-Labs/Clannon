# backend/ — backend agent pointer

The backend agent's full instructions live in the ROOT `CLAUDE.md` (role,
operating model, and the **Proposal Protocol**). Module-specific guardrails live
in each module's own `CLAUDE.md` (foundation/, core/*, security/*, registry/,
experts/, tools/, api/, delivery/).

## Your proposal inboxes — check at the START of every user interaction

- `../proposals/to-backend/` — requests from the FRONTEND agent.
- `./proposals/` — proposals from the OWNER to you.

Pending items: announce in one line ("N pending proposals: <slugs>"), then
handle per the root protocol. To ask the frontend for something, write
`../proposals/to-frontend/YYYY-MM-DD_slug.md` — never edit `frontend/`, never
route through the owner. Format: `../proposals/README.md`.
