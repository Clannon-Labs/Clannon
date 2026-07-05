#!/usr/bin/env bash
#
# clannon-standup.sh — one command to bring the whole crew online.
#
#   ./scripts/clannon-standup.sh
#
# For each of the four agents (backend, frontend, memory, orchestration): create
# its tmux session with the right cwd (if not already up) and launch Claude Code
# there in BYPASS-PERMISSIONS mode (--dangerously-skip-permissions), so none of
# them stops to ask the owner to approve tool calls. Then wake each with an
# [auto-wake] message so it runs its start-of-session inbox check and begins the
# day's work — the backend agent (the coordinator) gets the "start the day" call.
#
# Idempotent: a session that already exists is assumed to have Claude running, so
# it is NOT relaunched (that would type into a live session) — it is only woken.
# Attach any session with:  ./scripts/agent-session.sh <side>   (or tmux attach -t clannon-<side>)
#
# BYPASS PERMISSIONS IS DELIBERATE: the owner asked for it so the crew runs
# unattended. It is the same posture as the .claude/settings.local.json defaultMode.

set -uo pipefail   # no -e: a wake to one session must not abort the rest
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

sides=(backend frontend memory orchestration)

dir_for() {
  case "$1" in
    backend)       echo "$ROOT" ;;
    frontend)      echo "$ROOT/frontend" ;;
    memory)        echo "$ROOT/backend/core/memory" ;;
    orchestration) echo "$ROOT/backend/core/orchestrator" ;;
  esac
}

# The [auto-wake] prefix makes each agent treat the line as "check your inbox and
# act" per its CLAUDE.md. One line each — the real briefing is in their inboxes.
msg_for() {
  case "$1" in
    backend)
      echo "[auto-wake] Good morning — new work session. You've been woken up to start today's work. Read HANDOFF.md for state, check your inbox (proposals/to-backend/ + backend/proposals/), then drive the mission and coordinate the two specialists (memory, orchestration)." ;;
    frontend)
      echo "[auto-wake] New work session — check your inbox (proposals/to-frontend/ + frontend/proposals/) and continue your frontend work per your CLAUDE.md." ;;
    memory)
      echo "[auto-wake] New work session — check your inbox (proposals/to-memory/), read your kickoff + charter (core/memory/CLAUDE.md), and start/continue your work. Report to reports/memory/." ;;
    orchestration)
      echo "[auto-wake] New work session — check your inbox (proposals/to-orchestration/), read your kickoff + charter (core/orchestrator/CLAUDE.md), and start/continue your work. Report to reports/orchestration/." ;;
  esac
}

created=0
for side in "${sides[@]}"; do
  session="clannon-$side"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "clannon-standup: $session already up — will wake (not relaunching claude)."
  else
    dir="$(dir_for "$side")"
    tmux new-session -d -s "$session" -c "$dir"
    # type the launch command literally, then a detached Enter to submit it
    tmux send-keys -t "$session" -l "claude --dangerously-skip-permissions"
    sleep 0.3
    tmux send-keys -t "$session" Enter
    echo "clannon-standup: launched $session (cwd $dir) with bypass permissions."
    created=1
  fi
done

# Give any freshly-launched Claude instances time to boot before we type into them.
if [ "$created" = 1 ]; then
  echo "clannon-standup: waiting ~12s for new Claude instances to boot…"
  sleep 12
fi

# Wake each agent. Literal text + a separate Enter (a text+Enter burst is read as a
# paste and inserts a newline instead of submitting — same reason as proposal-wake.sh).
for side in "${sides[@]}"; do
  session="clannon-$side"
  tmux has-session -t "$session" 2>/dev/null || { echo "clannon-standup: $session missing — skipped wake."; continue; }
  tmux send-keys -t "$session" -l "$(msg_for "$side")"
  sleep 0.5
  tmux send-keys -t "$session" Enter
  echo "clannon-standup: woke $session."
done

echo "clannon-standup: crew online. Attach with ./scripts/agent-session.sh <backend|frontend|memory|orchestration>."
