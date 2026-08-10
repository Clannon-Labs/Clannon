# Clannon crew — operator instructions

Run everything from the repo root:

```bash
cd ~/Vault/projects/Clannon
```

Full design + reasoning: `docs/architecture/CREW_WORKFLOW.md`.

---

## Start an agent

```bash
./scripts/crew.sh start backend
```

Roles: `backend` `frontend` `memory` `orchestration` `security` `api`
`backend-audit` `frontend-audit` `release`

- Resumes that role's existing conversation if there is one; starts fresh
  otherwise.
- If the role is **already running**, it says so and changes nothing. It will
  never type into a session that is working.
- If a session is left over but its agent has exited ("dead-shell"), it
  recycles it automatically.

Options:

```bash
./scripts/crew.sh start api --codex    # run this role on Codex instead of Claude
./scripts/crew.sh start api --claude   # explicit Claude (this is the default)
./scripts/crew.sh start api --fresh    # ignore prior conversation, start clean
```

Every role, both audit roles included, is Claude unless you pass `--codex`.

### Start only what you need

There is no "start everything" command any more, on purpose. Six agents on one
box in one git tree caused memory pressure and collisions. **Backend alone is a
normal setup.** Add a specialist when there is work in its tree.

```bash
./scripts/crew.sh start backend
./scripts/crew.sh start api        # only if there's api/ work queued
```

---

## Audit roles are different

Independent security researchers, not implementers. `backend-audit` covers backend and
root infrastructure. `frontend-audit` covers browser/client surfaces using the
frontend-owned `frontend/FRONTEND_AUDIT_CHARTER.md`, and reads backend code only when a
frontend security claim depends on server enforcement. Both hunt realistic abuse and
working-as-designed control bypasses; scanners are only evidence inputs. Both write
findings only: no fixes, commits, pushes, or remote mutation.

```bash
./scripts/crew.sh start backend-audit           # Claude, like every role
./scripts/crew.sh start backend-audit --codex   # Codex
./scripts/crew.sh start frontend-audit
./scripts/crew.sh start frontend-audit --codex
```

`crew.sh` hands either role to `scripts/audit-sandbox.sh`, with role and provider as
parameters. Repository source, tests, config, `.git`, dependency manifests,
lockfiles, project environments, and auditor rules are mounted **read-only**. Writable
are only that role's notes/drafts, reports, own comms, handoff, and routed proposal
outputs. Normal home is absent: no SSH keys, `gh` token, cloud credentials, or owner
provider state.

That is the point: independence you do not have to trust a prompt for. If Bubblewrap is
missing, **it refuses to launch** rather than falling back to a polite request.

Prove the boundary after anything changes in that script:

```bash
./scripts/audit-sandbox.sh backend-audit self-test --codex
./scripts/audit-sandbox.sh backend-audit self-test --claude
./scripts/audit-sandbox.sh frontend-audit self-test --codex
./scripts/audit-sandbox.sh frontend-audit self-test --claude
```

It checks role outputs writable; source/`.git`/charter read-only; name resolution;
pinned scanners and project-aware tools visible; project configs parse without writes;
and provider startup against isolated state. Tools live below
`.agents/runtime/<role>/`, never project venv or `frontend/node_modules`.

Findings arrive in `reports/<role>/report_vN.md`. Backend findings route to
`proposals/to-backend/from-backend-audit/`; frontend findings route to frontend or
backend by actual fix ownership. Reports and proposals are gitignored: unfixed
vulnerability detail must not ship with source.

---

## See what's running

```bash
./scripts/crew.sh status
```

Shows each role's state (`running` / `dead-shell` / `stopped`), which provider
it's on, and how much was written to today's `comms/`.

---

## Watch an agent

```bash
./scripts/crew.sh attach backend
```

Detach with **`Ctrl-b`, then `d`**. The agent keeps working.

Do **not** type `exit` — that kills the agent. Detach instead.

You can type instructions to an agent yourself while attached; that's you
talking to it, which is fine. What no longer exists is *automation* typing into
sessions (see below).

---

## Stop an agent

```bash
./scripts/crew.sh stop memory
```

If an agent is live, this warns and waits 5s first (Ctrl-C aborts) — a killed
agent doesn't get to write its handoff. **Better: attach and ask it to stop
cleanly**, so it records where it got to in
`.agents/provider-handoffs/<role>.md`.

---

## What changed from the old setup

The old system pushed messages into agents' terminals automatically — a systemd
unit watched each inbox and typed into the session; another timer typed "are you
idle?" every 20 minutes. That is **all removed**. It garbled prompts, interrupted
agents mid-thought, and caused the coordinator to trample specialists that were
deliberately holding.

Now agents **pull**: they read `comms/<today>/` themselves when they start and
when they finish a piece of work. Nothing interrupts them.

Also gone: automatic Claude→Codex failover. The two don't share conversation
memory, so it never really "continued" anything — it just re-read a handoff,
which is what a normal restart does anyway. Now you pick the provider when you
start a role (`--codex`; Claude is the default), and an agent nearing its limit
writes its handoff and stops.

Old commands (`clannon-standup.sh`, `agent-session.sh`,
`clannon-provider-status.sh`, ...) are deleted. `crew.sh` covers all of it.

---

## Where the agents talk

| Location | What goes there | Tracked in git? |
|---|---|---|
| `comms/YYYY-MM-DD/<role>.md` | short status / notifications | **yes** |
| `proposals/to-<role>/` | decisions needing a ruling | no (local) |
| `reports/<role>/report_vN.md` | in-depth writeups | no (local) |

`comms/README.md` has the format. It's plain markdown — you can read and write
it yourself to leave the team notes.

---

## Typical session

```bash
./scripts/crew.sh start backend
./scripts/crew.sh status
./scripts/crew.sh attach backend      # Ctrl-b d to leave it running
```
