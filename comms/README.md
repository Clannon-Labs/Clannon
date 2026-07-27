# comms/ — the team's daily message log

Short status messages between agents. **Tracked in git** (unlike `proposals/`
and `reports/`, which are local working areas) — this is the durable record of
what the team did and said.

Full protocol: `docs/architecture/CREW_WORKFLOW.md` §3.

## Layout

```
comms/YYYY-MM-DD/<role>.md
```

One file per role per day. **You write only your own file.** Never edit
another role's. That is not just etiquette — it is why this design has no write
contention: several agents appending to one shared file in one git tree would
interleave and clobber.

Roles: `backend` `frontend` `memory` `orchestration` `security` `api`

## When to write here

| You want to... | Use |
|---|---|
| say what you did / flag something / hand off an observation | **`comms/`** (here) |
| get a **ruling** before you can proceed | `proposals/to-<role>/` |
| record the full detail of a finished piece of work | `reports/<role>/report_vN.md` |

## Entry format

Append a dated heading and a few lines. No ceremony, no required fields.

```markdown
## 14:20 — CB4 decision-mirror gap
Cancelled/crashed runs write zero decision records (the write only fires inside
the main try block). Affects: api/run_driver.py. Not fixing myself — flagged
for whoever owns it next. Depth: reports/api/report_v9.md
```

Name the role you need something from, so it is greppable:

```markdown
## 09:05 — need a ruling on the batch ceiling
@backend — filed proposals/to-backend/2026-07-27_batch-ceiling.md, blocked
until that lands. Picking up the graph-index work meanwhile.
```

## How this gets read

**Nothing notifies anyone.** No process types into your session; that whole
mechanism is gone and is not coming back (`CREW_WORKFLOW.md` §2.1).

You read `comms/<today>/` yourself:
- when you start a session, and
- when you finish a unit of work.

That is the contract. It means an agent mid-task is never interrupted, and it
means you are responsible for checking rather than waiting to be told.

## One rule that matters

**A `comms/` entry must be actionable on its own.** Link a report for depth if
you like, but `reports/` is gitignored — a fresh clone will not have it. If
someone needs a fact to act, put the fact here, not only in the link.
