@AGENTS.md

# Important directories
- frontend/proposals — proposals from the OWNER to you
- ../proposals — the cross-agent channel (you ↔ backend agent); format spec in ../proposals/README.md
- ../conversation — where you write reports and read from

> There is a separate instance for the backend so if you are not specifically
> assigned to work on the backend, NEVER make any changes on it.

> Important: YOU must be careful to not let any merge conflicts happen or,
> Overwrite the work of the backend agent !!

## Proposal Protocol (full spec: root CLAUDE.md §PROPOSAL PROTOCOL)

**At the START of every user interaction, BEFORE anything else, check your
inboxes:** `../proposals/to-frontend/` (from the backend agent) and
`frontend/proposals/` (from the owner). If pending proposals exist, tell the
owner in one line — "N pending proposals: <slugs>" — then handle them per their
Priority (unless the owner's current request is urgent; then ask which comes
first). When done: append your `## Response`, flip Status, move the file to
`../proposals/archive/to-frontend/`.

When YOUR work needs something from the backend (an endpoint, a contract
change, new data in a response): write `../proposals/to-backend/
YYYY-MM-DD_slug.md` and design around the gap until answered. Never edit
backend code; never ask the owner to relay. Proposals are the ONLY channel.