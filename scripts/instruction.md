# Clannon crew — operator instructions

Run commands from repository root:

```bash
cd ~/Vault/projects/Clannon
```

## Start or restore whole crew

```bash
./scripts/clannon-standup.sh dual
```

This is normal one-command startup.

- Covers `backend`, `frontend`, `memory`, `orchestration`, `security`, and `api`.
- Resumes latest provider-native sessions when possible.
- Tries Claude Code first.
- Confirmed Claude usage limit switches role to Codex.
- Confirmed Codex limit returns to Claude when available.
- Reads role handoff, shared provider handoff, inbox, reports, and Git state.
- If any live/attached agent is detected, changes nothing and reports active role.
- If all old tmux sessions are missing or stale idle shells, removes stale shells
  and recreates crew automatically.

## Check which provider each role uses

```bash
./scripts/clannon-provider-status.sh
```

## Watch agent in terminal

Attach one session:

```bash
tmux attach -t clannon-backend
tmux attach -t clannon-frontend
tmux attach -t clannon-memory
tmux attach -t clannon-orchestration
tmux attach -t clannon-security
tmux attach -t clannon-api
```

Use separate terminal tab/window for each role you want to watch.

Detach without stopping agent:

```text
Ctrl-b, then d
```

Do not type `exit` when you only want to stop watching. `exit` terminates current
provider/session; tmux detach keeps it working.

## Attach helper

Equivalent helper:

```bash
./scripts/agent-session.sh backend
./scripts/agent-session.sh frontend
./scripts/agent-session.sh memory
./scripts/agent-session.sh orchestration
./scripts/agent-session.sh security
./scripts/agent-session.sh api
```

## Start selected roles only

```bash
./scripts/clannon-standup.sh dual memory orchestration security api
```

## Important messages

`active crew detected — no sessions changed`

: At least one selected tmux pane is attached or running work. Existing work was
  protected. Attach/status-check it; rerun after active agent exits if restart is
  intended.

`removed stale idle shell`

: Claude/Codex exited but tmux shell remained. Script safely removed stale shell
  before relaunch.

`starting claude`

: Supervisor is trying/resuming Claude Code.

`starting codex`

: Claude is limited/unavailable, or role was explicitly restarted Codex-first.

## Normal daily flow

```bash
./scripts/clannon-standup.sh dual
./scripts/clannon-provider-status.sh
tmux attach -t clannon-backend
```

Detach with `Ctrl-b`, then `d`. Crew continues working.
