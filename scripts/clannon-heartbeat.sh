#!/usr/bin/env bash
#
# clannon-heartbeat.sh <backend|frontend|memory|orchestration> — the KEEP-ALIVE
# ping. Fired by a systemd --user TIMER (clannon-heartbeat@<side>.timer →
# .service) every ~20 minutes so an agent that has gone idle NEVER sleeps
# permanently. This is the guarantee the inbox-triggered wake (proposal-wake.sh)
# cannot give on its own: that one only fires when the inbox CHANGES, so a quiet
# inbox + a broken self-armed ScheduleWakeup chain would leave the agent asleep
# forever. The timer closes that gap — it is external to the agent, survives a
# session restart / crash / reboot, and does not depend on the agent remembering
# to re-arm itself.
#
# Primary target is the BACKEND (the coordinator): if it sleeps, the whole team
# stalls (it is the hub that feeds the specialists). Templated per-side so the
# same unit can keep any agent alive if wanted.
#
# NEVER invokes claude / claude -p / any AI process. The ONLY action is one
# `tmux send-keys` into the live interactive session the owner already runs —
# identical safety posture to proposal-wake.sh.

set -uo pipefail   # deliberately no -e: every exit path below must be clean

SIDE="${1:?usage: clannon-heartbeat.sh backend|frontend|memory|orchestration}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="clannon-$SIDE"

log() { echo "clannon-heartbeat[$SIDE]: $*"; }   # goes to the user journal

# Target session gone (agent not running)? Log once, exit clean — never error,
# never retry. The next `clannon-standup.sh` (or the owner) brings it back, and
# the agent re-orients from docs/RESUME.md + its handoff on launch.
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  log "session $SESSION not running — skipped (nothing to keep alive)"
  exit 0
fi

# The keep-alive message. Self-contained so a FRESH session (empty live context)
# knows exactly what to do; harmless if the agent is already busy (Claude Code
# queues the line and processes it after the current turn). Phrased so a healthy,
# fully-busy team produces no churn — the agent only acts if something is idle or
# unpushed. Per-side so a specialist ping tells IT to resume its own track.
case "$SIDE" in
  backend)
    MSG="[COORDINATOR HEARTBEAT · auto keep-alive] 20-min tick so you never sleep permanently. Run your coordinator sweep: if your live context is empty (fresh session) FIRST read docs/RESUME.md to reload state; then check proposals/to-backend/, capture-pane clannon-memory + clannon-orchestration and feed any IDLE specialist a next step, push any unpushed commits ONLY after the suite is green (sole pusher, explicit pathspec), advance the mission/config/foundation work, and re-arm your ScheduleWakeup. If everyone is busy and nothing is unpushed, do nothing noisy — just confirm and go quiet." ;;
  *)
    MSG="[HEARTBEAT · auto keep-alive] 20-min tick so you never sleep. If idle: re-read your handoff (HANDOFF*.md in this dir) + charter + inbox and continue your track; if mid-task, ignore this. Report to reports/$SIDE/." ;;
esac

# Same tmux idiom as proposal-wake.sh: `-l` types the text LITERALLY (never
# misread as a key name), then a SEPARATE Enter after a beat — a text+Enter burst
# is read by the TUI as a paste (inserts a newline instead of submitting).
tmux send-keys -t "$SESSION" -l "$MSG"
sleep 0.5
tmux send-keys -t "$SESSION" Enter
log "pinged $SESSION (keep-alive)"
