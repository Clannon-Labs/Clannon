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

sides=(backend frontend memory orchestration security)

dir_for() {
  case "$1" in
    backend)       echo "$ROOT" ;;
    frontend)      echo "$ROOT/frontend" ;;
    memory)        echo "$ROOT/backend/core/memory" ;;
    orchestration) echo "$ROOT/backend/core/orchestrator" ;;
    security)      echo "$ROOT/backend/security" ;;
  esac
}

# The [auto-wake] prefix makes each agent treat the line as "check your inbox and
# act" per its CLAUDE.md. One line each — the real briefing is in their inboxes.
msg_for() {
  case "$1" in
    backend)
      echo "[auto-wake] RESUMING — this is a fresh session, so your live context is empty; the durable state is on disk/GitHub. FIRST read docs/RESUME.md (the committed resume runbook) + .claude/contexts/HANDOFF.md (local anchor) to reload full state, THEN check your inbox (proposals/to-backend/ + backend/proposals/), re-arm the coordinator heartbeat (ScheduleWakeup ~1200s), and drive the mission + coordinate the two specialists (memory, orchestration). Continue from where the runbook says, don't restart." ;;
    frontend)
      echo "[auto-wake] RESUMING (fresh session) — FIRST read your handoff HANDOFF.md (in this dir) to pick up where you paused, THEN check your inbox (proposals/to-frontend/ + frontend/proposals/) and continue your frontend work per your CLAUDE.md." ;;
    memory)
      echo "[auto-wake] RESUMING MID-TASK (fresh session — live context is empty). FIRST read your handoff HANDOFF_batch.md (in this dir) to pick up EXACTLY where you paused on the Mission Engine graph build (members()/mission_graph_store — what's done + the next steps), THEN your charter (core/memory/CLAUDE.md) + inbox (proposals/to-memory/). Continue from the handoff's next-steps — do NOT restart from scratch. Report to reports/memory/." ;;
    orchestration)
      echo "[auto-wake] RESUMING (fresh session — live context is empty). FIRST read your handoff HANDOFF_mission.md (in this dir) to pick up your Mission Engine state + what unblocks now that memory's members() landed, THEN your charter (core/orchestrator/CLAUDE.md) + inbox (proposals/to-orchestration/). Continue from the handoff — do NOT restart. Report to reports/orchestration/." ;;
    security)
      echo "[auto-wake] RESUMING (fresh session — live context is empty). FIRST read your charter (backend/security/CLAUDE.md) + inbox (proposals/to-security/), THEN continue your config-wire (settings.SECURITY.*) + CB5 work and stand as invariant reviewer for the budget/batch designs. Do NOT restart from scratch. Report to reports/security/." ;;
  esac
}

# --- Mode -------------------------------------------------------------------
# resume : bring back the EXACT running conversations — `claude --continue` in each agent's own
#          cwd, so no context is lost and no reorientation is needed. This is what you run after
#          closing the terminals or rebooting: every agent picks up its exact session.
# fresh  : cold-start a NEW session per agent + send the reorientation wake (read handoff). Only
#          for a true cold clone where no prior session exists on disk.
MODE="${1:-fresh}"
case "$MODE" in resume|fresh) ;; *) echo "usage: $(basename "$0") [resume|fresh]"; exit 2 ;; esac
echo "clannon-standup: mode = $MODE"

created=0
for side in "${sides[@]}"; do
  session="clannon-$side"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "clannon-standup: $session already up — will wake (not relaunching claude)."
  else
    dir="$(dir_for "$side")"
    # Model tiering: the two backend SPECIALISTS (implementors) run on Sonnet 5 to
    # cut token burn; backend (coordinator/reviewer/net) + frontend stay on their
    # default (Opus). The quality net is the backend agent's Opus review of every
    # specialist proposal + merge — not the model. Reversible: drop the flag to
    # bump a specialist back to Opus.
    # `--continue` (resume) picks the most-recent session for this cwd = the agent's live one.
    launch="claude --dangerously-skip-permissions"
    [ "$MODE" = resume ] && launch="$launch --continue"
    # Keep the specialist model tier explicit in BOTH modes (don't rely on resume remembering it —
    # a specialist silently resuming on Opus would blow the token budget the tiering exists to save).
    case "$side" in
      memory|orchestration|security) launch="$launch --model claude-sonnet-5" ;;
    esac
    tmux new-session -d -s "$session" -c "$dir"
    # type the launch command literally, then a detached Enter to submit it
    tmux send-keys -t "$session" -l "$launch"
    sleep 0.3
    tmux send-keys -t "$session" Enter
    echo "clannon-standup: launched $session (cwd $dir) [$launch]."
    created=1
  fi
done

# Give any freshly-launched Claude instances time to boot before we type into them.
if [ "$created" = 1 ]; then
  echo "clannon-standup: waiting ~12s for new Claude instances to boot…"
  sleep 12
fi

# Wake each agent (FRESH mode only). A resumed agent already has its full context, so injecting a
# reorientation message would be wrong (and could type over you) — resume just brings the sessions
# back; the heartbeat + inbox-path units re-engage the coordinator, and you can type into any
# session to drive. Literal text + a separate Enter (a text+Enter burst is read as a paste and
# inserts a newline instead of submitting — same reason as proposal-wake.sh).
if [ "$MODE" = fresh ]; then
  for side in "${sides[@]}"; do
    session="clannon-$side"
    tmux has-session -t "$session" 2>/dev/null || { echo "clannon-standup: $session missing — skipped wake."; continue; }
    tmux send-keys -t "$session" -l "$(msg_for "$side")"
    sleep 0.5
    tmux send-keys -t "$session" Enter
    echo "clannon-standup: woke $session."
  done
else
  echo "clannon-standup: resume mode — contexts intact, no reorientation wake sent."
fi

# Keep-alive guarantee: (re)install + enable the 20-min heartbeat timer so the
# BACKEND coordinator never sleeps permanently — even on a fresh clone after a
# disk loss, and independent of the agent's own ScheduleWakeup. Idempotent: cp
# overwrites, `enable --now` is a no-op if already enabled. The inbox-triggered
# clannon-wake@backend.path only fires on inbox CHANGES; this timer is the
# unconditional floor. (See scripts/systemd/clannon-heartbeat@.timer.)
if command -v systemctl >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cp "$ROOT/scripts/systemd/clannon-heartbeat@.service" \
     "$ROOT/scripts/systemd/clannon-heartbeat@.timer" "$HOME/.config/systemd/user/" 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
  if systemctl --user enable --now clannon-heartbeat@backend.timer 2>/dev/null; then
    echo "clannon-standup: heartbeat timer enabled (backend never sleeps > 20 min)."
  else
    echo "clannon-standup: WARN could not enable heartbeat timer (systemd --user unavailable?) — arm ScheduleWakeup in-agent instead."
  fi
fi

echo "clannon-standup: crew online ($MODE). Attach with:  tmux attach -t clannon-<backend|frontend|memory|orchestration|security>"
echo "clannon-standup:   (or ./scripts/agent-session.sh <side>).  Re-run any time — alive sessions are left untouched."
