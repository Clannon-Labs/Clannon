# `requests/` — frontend asks, backend builds

**This is the only place in `specification/` the frontend writes.**

The frontend must never be blocked waiting for the backend to notice something.
File a request here, keep building against the mock, and the backend picks it up on
its next inbox sweep. A request in this directory is tracked and pushed, so it reaches
any session on any machine — unlike `proposals/`, which is gitignored and never
leaves the machine that wrote it.

## How

1. Copy [`TEMPLATE.md`](TEMPLATE.md) to `YYYY-MM-DD_short-slug.md`.
2. Fill it in. Be concrete about the response shape — a vague request costs a round
   trip, and a round trip here is a day, not a minute.
3. Commit it. Add a line to `comms/<today>/frontend.md` so the backend sees it without
   having to poll.
4. Keep going. Mock the route in `src/lib/api/mock.ts` and build the UI against it —
   do not idle on the answer.

## What happens next

| Backend does | Then |
|---|---|
| Builds it | Adds it to `../ROUTES.md`, appends `## Response` here, flips `Status: DONE`, moves the file to `archive/` |
| Declines or changes the shape | Appends `## Response` with the reason and the counter-proposal, sets `Status: NEEDS DISCUSSION` |
| Cannot do it yet | Appends `## Response` with what it is blocked on, sets `Status: BLOCKED` |

The backend answers **every** request. Silence is a bug — say so in `comms/`.

## Rules

- **One route per file.** Two routes in one file means one of them stalls behind the
  other's discussion.
- **Frontend does not edit `../ROUTES.md`.** A route lands there when it is built and
  reachable, never when it is wanted. A route table that lists things the code does
  not serve is worse than no table, because it is trusted.
- **Backend does not edit a request's body**, only appends `## Response`. The ask is
  the frontend's record of what it needed.
- **Say whether you are blocked.** `Blocking: yes` means real work has stopped and it
  gets priority. Using it when a mock would do burns the signal.
