# Crew workflow — how the agents on this repo actually work

**Status: CANONICAL.** This supersedes every earlier description of agent
coordination (the `Wake:` protocol, `[auto-wake]` messages, the heartbeat
timers, the provider-failover supervisor). Where an older doc disagrees with
this file, this file wins and the older doc is wrong and should be fixed.

Written 2026-07-27 by the backend agent, on the owner's explicit instruction to
redesign from scratch rather than bolt more fixes onto a weak base.

---

## 0. Why this was rewritten — the honest post-mortem

The previous system worked by **pushing**: a systemd path unit watched each
inbox directory, and on any change it ran `tmux send-keys` to type a message
directly into that agent's live terminal session. A second systemd timer typed
a "you might be idle" prompt into the coordinator every 20 minutes. The
coordinator also re-armed its own wakeup loop on top of both.

Every serious problem we hit traces back to that design:

| Symptom | Root cause |
|---|---|
| Garbled/half-submitted prompts in agent sessions | `send-keys` types into whatever the TUI is doing. A multi-line message during an active turn interleaves with the agent's own input. |
| Coordinator "helpfully" submitting a specialist's queued command | The idle-detection prompt told the coordinator to treat any quiet pane as a stall. Specialists that were *deliberately* holding were interrupted. |
| Manufactured busywork, git churn, collision risk | The standing policy said "the team NEVER sits idle — not a second wasted." That is a bad policy (see §2.2). |
| Three different things could wake one agent | systemd path unit + systemd timer + in-agent self-scheduled wakeup, all live simultaneously, none aware of the others. |
| Coordinator doing implementation instead of coordinating | No structural pressure to delegate; the fast path was always "just build it myself." |
| Specialists blocked from committing their own work | Provider sandboxes were configured inconsistently and denied `.git/` and `.agents/` writes. |

**The single worst offender was the no-idle policy.** It is the clearest case of
an instruction that sounded like it maximised output and actually cost us
tokens, produced throwaway work, and caused agents to step on each other. It is
explicitly retired in §2.2.

---

## 1. Roles

| Role | Session name | Owns (exclusive edit rights) |
|---|---|---|
| **backend** (coordinator) | `clannon-backend` | repo root, `backend/foundation/`, `backend/core/pipeline.py`, `backend/delivery/`, `config/`, `backend/settings.py`, `docs/`, `scripts/` |
| **frontend** | `clannon-frontend` | `frontend/` |
| **memory** | `clannon-memory` | `backend/core/memory/` |
| **orchestration** | `clannon-orchestration` | `backend/core/orchestrator/`, `backend/registry/`, `backend/experts/`, `backend/tools/` |
| **security** | `clannon-security` | `backend/security/` |
| **api** | `clannon-api` | `backend/api/` |

Exclusive means exclusive: **no agent edits another's tree, ever** — not even a
one-line "obvious" fix. Cross-tree needs go through a proposal (§3.2). The
backend agent has final integration authority and is the **sole pusher**, but
being coordinator does not grant edit rights into a specialist's tree.

Each role's detailed charter lives in the `CLAUDE.md` of the tree it owns.

---

## 2. Principles

These are the rules the machinery exists to serve. If a script ever conflicts
with a principle, the script is wrong.

### 2.1 Pull, never push

**Nothing may inject input into a running agent's session. Ever.** No
`tmux send-keys`, no systemd unit typing into a pane, no automated prompt
injection of any kind.

Agents read their inbox at **natural boundaries** — when starting a session,
and when they finish a unit of work. Not when something external decides they
should.

This is the rule the whole redesign hangs on. An agent's turn is not
interruptible by design; pretending otherwise is what produced garbled input
and trampled work.

### 2.2 Idle is a healthy state

**Retired policy:** "the team never sits idle, not a second wasted."

An idle agent costs nothing. An agent doing manufactured work costs tokens,
creates git churn, invents surface area nobody asked for, and raises the odds
of colliding with someone doing real work. An agent that has finished its
queue and has nothing genuinely queued should **write its handoff and stop.**

"Is there real work?" is a question with a legitimate "no" answer.

### 2.3 One mechanism per purpose

Three channels, non-overlapping (§3). Anything that feels like it needs a
fourth is a sign the boundary between the existing three is being misused.

### 2.4 The coordinator coordinates

The backend agent's job is planning, architecture, rulings, review, and
integration. When work fits a specialist's tree, it is **assigned**, not
absorbed. The coordinator implements only what is genuinely its own (the
shared seams: `foundation/`, the pipeline, config, docs, scripts).

### 2.5 Right model for the job

See §5. Claude designs and reviews; Codex implements from a written brief.

### 2.6 The owner's instruction is strong, not absolute

See §6.

---

## 3. The three channels

### 3.1 `comms/` — status, notifications, "here's what I did"

```
comms/YYYY-MM-DD/<role>.md
```

- **One file per role per day.** Sharded deliberately: several agents appending
  to one shared daily file in one git tree will interleave and clobber. Each
  agent writes only its own file, so there is no write contention at all.
- **Tracked in git.** This is the durable record of what the team did and said.
  (`proposals/` and `reports/` are gitignored working areas — see below. If it
  matters tomorrow, it goes in `comms/`.)
- **Short.** A few lines per entry. What happened, what it affects, what (if
  anything) you need from someone. Link to a report for depth.
- **Append-only within your own file.** Never edit another role's file.

Entry format — plain, no ceremony:

```markdown
## 14:20 — CB4 decision-mirror gap
Cancelled/crashed runs write zero decision records (the write only fires inside
the main try block). Affects: api/run_driver.py. Not fixing myself — flagged
for whoever owns it next. Depth: reports/api/report_v9.md
```

The backend agent reads `comms/<today>/` at the start of a session and after
finishing a unit of work. So does everyone else, for the entries that name them.

### 3.2 `proposals/to-<role>/` — decisions that need a ruling

Unchanged in shape, with one deletion: **the `Wake:` header field is gone**
(it existed only to feed the auto-injection that no longer exists).

Use a proposal when you need a **decision before you can proceed** — a contract
change, a cross-tree edit, a design that has a real tradeoff. Not for status;
that is `comms/`.

Lifecycle unchanged: write to the target's inbox → they append `## Response`,
flip `Status:` → move to `proposals/archive/<inbox>/`.

Gitignored (working area). If a ruling has lasting consequence, the decision
gets recorded in `comms/` or promoted into `docs/`.

`proposals/to-owner/` is the sole owner-reply channel. One decision per file,
same headers as every proposal, with an authority-level body: context, exact
decision, options/consequences, recommendation, and unblock. Settled owner
proposals move to `proposals/archive/to-owner/`.

### 3.3 `reports/<role>/report_vN.md` — depth

Unchanged. One new file per finished piece of work. Gitignored, local, high
churn by design.

**`<role>/` means every role, coordinator included** (tidied 2026-07-28 on the
owner's instruction). The backend agent used to drop its `report_vN.md` at the
root of `reports/` while every specialist filed under its own folder, which made
the root a mixed pile of eighteen coordinator reports and the owner's files. The
coordinator's now live in `reports/backend/`.

The root of `reports/` is reserved for information shared by everyone, not one
role's working depth:

| File | What it is |
|---|---|
| — | the shared backend↔frontend contract moved to `specification/api/` on 2026-08-02; `reports/` is per-role folders only |

Reports are information-only. Nothing under `reports/` requests action or
implies a reply; owner decisions use `proposals/to-owner/`.

**Rule:** a `comms/` entry must be actionable on its own. A report link is
convenience, not a dependency — a fresh clone that has no `reports/` must still
be able to act on what `comms/` says.

### 3.4 Promotion path

```
comms/ (tracked, short, durable)  →  docs/ (tracked, canonical)
reports/ (local, deep, working)   ↗
proposals/ (local decisions)      ↗
```

Anything that turns out to be a lasting architectural fact gets written into
`docs/`. That is the only tier that outlives the working files.

---

## 4. Running the crew

### 4.1 tmux is for persistence and watching — not for messaging

tmux stays, for exactly two reasons: sessions survive a disconnect, and the
owner can attach to watch an agent work. **Nothing types into a pane.** Attach
is read-only in spirit — if you want to give an agent instructions, you are
free to type them yourself as the owner; no automation may.

### 4.2 Launch deliberately, not as a standing crew

Six agents running simultaneously on one 24 GB box, in one shared git tree, was
a persistent source of OOM pressure and cross-agent collisions. The default is
now: **start the roles you actually need for the work at hand.**

The backend agent alone is a perfectly normal configuration. So is backend plus
one specialist. All six at once should be a deliberate choice, not a default.

### 4.3 Commands

```bash
./scripts/crew.sh start <role> [--codex]   # start (or resume) one role
./scripts/crew.sh status                   # what's running, and under which provider
./scripts/crew.sh attach <role>            # watch a session (Ctrl-b d to detach)
./scripts/crew.sh stop <role>              # stop one role cleanly
```

`start` resumes the role's existing conversation when one exists, and starts
fresh otherwise. It never types into a session that is already running — if the
role is up, it says so and does nothing.

### 4.4 Two ways an agent runs — interactive vs. delegated

These do not overlap, and neither injects into a live session, so §2.1 holds for
both.

| | `start` / `attach` | `run` |
|---|---|---|
| Shape | interactive session in tmux | headless one-shot worker |
| Who drives it | **the owner** | **the coordinator** |
| Lifetime | until stopped | exits when the task is done |
| tmux? | yes | **none** |

```bash
./scripts/crew.sh run <role> --brief <file> [--claude|--codex]
```

This is how the coordinator gets work done without doing it. Write a brief
(§5.3) under `.agents/briefs/<role>/`, dispatch it into a role's tree, then read
the worker's final message from `.agents/runs/<stamp>-<role>.out`. If the next
step needs it, cite that output in the next worker's brief. **Chaining needs no
machinery**: it is one file read and one file write. Do not build a job queue.

**Because `run` needs no tmux, the owner only ever has one session open: the
coordinator's.**

Rules the dispatcher enforces structurally, so they cannot be forgotten:

- **Workers never commit or push.** Every brief gets a mandate appended
  automatically. Two workers racing on `.git/index.lock` is a failure we have
  already hit once; the coordinator reviews and commits, which is its job
  anyway.
- **One worker per role.** A lock file per role; roles own disjoint trees, so
  that is all the mutual exclusion needed.
- **No dispatch into a dirty tree.** If the coordinator left uncommitted changes
  in that role's tree, the worker's diff would be unreviewable. Refuses with a
  clear message.
- **Always fresh.** No headless resume — a self-contained brief is the contract,
  and resuming reintroduces the wrong-session risk §5.4 removes.
- **Provenance is automatic.** The dispatcher (not the worker, which could
  forget) records role, provider, brief, exit status, duration, and output path
  — full logs to gitignored `.agents/runs/`, one tracked line to
  `comms/<today>/backend.md`. That is how "who did what" stays answerable.
- **Worker identity and proposal routing are explicit.** A backend-owned worker
  is `backend-worker`; proposals it raises for the persistent coordinator go to
  `proposals/to-backend/from_workers/`. A specialist worker is
  `<role>-worker` (`api-worker`, `memory-worker`, etc.); its proposals go to
  `proposals/to-backend/`. Every worker addresses `backend-coordinator`.
  Coordinator-to-worker dispatch briefs live under `.agents/briefs/<role>/`,
  never in proposal inboxes.

**Provider choice.** Explicit `--claude` / `--codex` always wins. Otherwise the
dispatcher reads `.agents/provider-policy` — a one-line default with the reason
and a revisit condition written next to it, so a temporary budget decision
cannot quietly become permanent policy.

### 4.5 Subagents vs. headless workers vs. interactive roles

Both Claude Code and Codex can spawn **built-in subagents** inside a session.
That is a third option, and the honest question is why the other two exist.

| | Built-in subagent | Headless worker (`run`) | Interactive role (`start`) |
|---|---|---|---|
| Lives in | the caller's session | its own process | its own tmux session |
| Provider | **same as caller** | **either** (`--codex`) | either |
| Token budget | the caller's | separate | separate |
| Result lands | **in the caller's context** | in a file the caller chooses to read | on screen, for the owner |
| Durable identity | none | role charter + handoff + comms | same |
| Survives the turn | no | yes (can run for minutes) | yes (indefinitely) |
| Driven by | the caller | the coordinator | **the owner** |

**Use a subagent** for a fast, read-only question whose answer you want
immediately in context — "where is this symbol defined", "which files reference
X". It is the lowest-ceremony option and for lookups it is genuinely the best
one. Don't build a file-passing dance around a question you could just ask.

**Use a headless worker** for real implementation. Three concrete advantages a
subagent cannot give:

1. **A different provider and a separate budget.** Subagents run on the caller's
   provider and spend the caller's tokens. A headless worker can be Codex, which
   is the whole reason the coordinator can delegate implementation without
   burning the Claude budget it needs for review and architecture.
2. **Context cost is opt-in.** A subagent's report returns into the caller's
   context whole. A worker's output sits in a file — the coordinator reads the
   twenty lines that matter and leaves the rest on disk. On a long coordination
   session this is the difference between finishing and compacting.
3. **A durable role identity.** A worker inherits a charter, a tree it exclusively
   owns, a handoff file, and a comms trail. A subagent has none of that — it
   cannot be held to an ownership boundary across time, and there is no record
   afterwards of what it was or what it touched.

**Use an interactive role** when the *owner* wants to drive an agent
conversationally — course-correcting mid-task, or working a long arc where the
accumulated conversation is itself the value. The `release` role is exactly
this case.

The three are complements, not competitors: subagent = look something up;
worker = get something built; interactive = talk to a specialist.

---

## 5. Provider strategy — Claude and Codex

The owner asked how to actually take advantage of having both. The answer comes
from what demonstrably worked, not from the spec sheet.

### 5.1 What we observed

Codex was used twice in one session. Both succeeded, and both had the same
shape: **a written brief with a precise problem statement, explicit
constraints, verification criteria, and "do not commit."** It found a root
cause the coordinator had guessed wrong about (an inherited `errexit`, not a
clobbered `$?`), built its own repro harness, and stayed exactly in scope.

Where it got stuck was self-direction under ambiguity and sandbox limits — it
could not commit its own work and had to write a fallback report instead.

### 5.2 The division

| | Claude | Codex |
|---|---|---|
| **Coordinator (backend)** | always | never |
| Architecture, planning, rulings, review | yes | no |
| Scoped implementation from a spec | fine | **preferred** — faster, stays in scope |
| Debugging a specific failure | fine | **preferred** |
| Open-ended "figure out what to do next" | yes | avoid |

### 5.3 The brief is the interface

When handing work to Codex, write a brief containing:

1. **The problem** — concrete, with the symptom and where it shows.
2. **What to change** and what is explicitly out of scope.
3. **How to verify** — the exact command, the expected result.
4. **Boundaries** — which files it may touch; which trees are someone else's.
5. **"Do not commit or push."** The backend agent reviews and commits.

A brief this shape is what made both Codex tasks land cleanly. An
under-specified brief is the failure mode.

### 5.4 No automatic mid-session failover

The old supervisor watched panes for usage-limit text, waited five minutes to
confirm, killed the provider, and relaunched the other one. **This is removed.**

It was ~12 KB of fragile machinery serving a goal it could not actually reach:
the two providers do not share conversation memory, so "continuing where the
other left off" always meant re-reading handoff files anyway. It also depended
on scraping a TUI for English strings, which breaks whenever either vendor
rewords a message.

**Instead:** an agent approaching its limit writes its handoff and stops
(§7). The next session — either provider — picks up from that handoff. This is
the same recovery path as any other restart, which means it is a path we
exercise constantly instead of a special case that only runs during an
emergency.

---

## 6. Challenging the owner

The owner is the ultimate authority and is owed directness, not compliance
theatre.

**Before acting on an instruction, confirm it will actually benefit the team.**
If it will not, say so plainly, explain why, propose the alternative — and then
follow the owner's decision if they reaffirm it. Disagreement goes *before* the
work, not after it as an excuse.

This is not hypothetical politeness. It is written here because we have a
concrete, expensive example: **the "never sits idle" policy.** It was issued in
good faith to keep the team productive. Its actual effects were manufactured
busywork, wasted tokens, git churn, and agents interrupting each other's real
work. Nobody pushed back on it for days. That silence cost more than any
disagreement would have.

The lesson generalises: an instruction that optimises a proxy metric
(utilisation) instead of the goal (working software) should be challenged the
first time it is heard.

---

## 7. Handoffs and stopping cleanly

Every role keeps a handoff at `.agents/provider-handoffs/<role>.md` (tracked).

**Before stopping** — planned exit, context running low, or a usage limit in
sight — update it:

- what you were doing and how far you got
- what is committed vs. still dirty in the tree
- what the next session should do first
- anything explicitly *not* to do, and why

Preserve the prior entry under `## Previous checkpoint`, and say what changed
under `## Change note`. A cold session — possibly the other provider, with zero
context — must be able to resume from this file alone.

**Stopping is normal.** A clean stop with a good handoff is a better outcome
than a session that runs on empty and leaves a mess.

---

## 8. What was removed

For anyone reading an older doc or commit and wondering where something went:

| Removed | Why |
|---|---|
| `scripts/proposal-wake.sh` | Push-based injection (§2.1). |
| `scripts/clannon-heartbeat.sh` | Idle-policing (§2.2) via injection (§2.1). |
| `scripts/systemd/clannon-wake@.{path,service}` | Same. |
| `scripts/systemd/clannon-heartbeat@.{service,timer}` | Same. |
| `scripts/clannon-standup.sh` | Mass-launch + wake injection; replaced by `crew.sh` (§4.3). |
| `scripts/clannon-provider-supervisor.sh` | Automatic failover (§5.4). |
| `scripts/clannon-provider-status.sh` | Folded into `crew.sh status`. |
| `scripts/agent-session.sh` | Folded into `crew.sh attach`. |
| `Wake:` proposal header | Fed the injection that no longer exists. |
| In-agent `ScheduleWakeup` coordinator loop | Third overlapping wake mechanism (§2.3). |
