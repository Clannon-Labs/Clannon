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

# --- BACKEND idle-gating (owner request 2026-07-06) -------------------------------
# The coordinator only has work to do — feed an idle specialist, push their finished
# commits — when the specialists are NOT actively building. So instead of a blind
# fixed-interval tick, the timer polls often but this gate fires the ping only when
# ALL specialists (memory + orchestration) are idle, and only ONCE per idle period.
# A specialist is "working" iff its tmux pane shows Claude Code's `esc to interrupt`
# hint (present only while a turn is generating; a completed-turn summary line is not).
# A long fallback still guarantees the coordinator is never stranded asleep — even if
# a specialist builds for hours or the pane check ever misreads.
if [ "$SIDE" = "backend" ]; then
  # If the coordinator itself is mid-turn, it needs no nudge — it'll finish and re-sweep.
  if tmux capture-pane -t "$SESSION" -p 2>/dev/null | grep -q "esc to interrupt"; then
    log "skip — coordinator is itself busy"
    exit 0
  fi

  IDLE_STAMP="/tmp/clannon-heartbeat-backend.idle-pinged"  # set once pinged for the current idle period
  LAST_PING="/tmp/clannon-heartbeat-backend.last-ping"     # unix ts of last ping (fallback clock)
  FALLBACK_S=3600                                          # never let >1h pass with zero pings
  now="$(date +%s)"
  last="$(cat "$LAST_PING" 2>/dev/null || echo 0)"
  since=$(( now - last ))

  working=""
  for peer in memory orchestration; do
    if tmux has-session -t "clannon-$peer" 2>/dev/null \
       && tmux capture-pane -t "clannon-$peer" -p 2>/dev/null | grep -q "esc to interrupt"; then
      working="$working $peer"
    fi
  done

  if [ -n "$working" ]; then
    # A specialist is building — clear the idle marker so the NEXT all-idle transition
    # re-fires, and stay silent unless the fallback window has elapsed (marathon safety net).
    rm -f "$IDLE_STAMP"
    if [ "$since" -lt "$FALLBACK_S" ]; then
      log "skip — busy:$working (idle-gated; ${since}s < ${FALLBACK_S}s fallback)"
      exit 0
    fi
    log "fallback nudge — busy:$working but ${since}s elapsed (safety net)"
  else
    # All specialists idle — nudge ONCE per idle period (the stamp suppresses re-pinging
    # on every poll while they stay idle).
    if [ -e "$IDLE_STAMP" ]; then
      log "skip — all idle but already nudged this idle period"
      exit 0
    fi
    : > "$IDLE_STAMP"
    log "all specialists idle — nudging coordinator"
  fi
  echo "$now" > "$LAST_PING"
fi

# The keep-alive message. Self-contained so a FRESH session (empty live context)
# knows exactly what to do; harmless if the agent is already busy (Claude Code
# queues the line and processes it after the current turn). Phrased so a healthy,
# fully-busy team produces no churn — the agent only acts if something is idle or
# unpushed. Per-side so a specialist ping tells IT to resume its own track.
case "$SIDE" in
  backend)
    MSG="[COORDINATOR HEARTBEAT · specialists idle] The specialists have gone idle (or this is the hourly safety fallback), so there may be coordination to do. Run your sweep: if your live context is empty (fresh session) FIRST read docs/RESUME.md to reload state; then check proposals/to-backend/, capture-pane clannon-memory + clannon-orchestration and feed any IDLE specialist a next step (deliver rulings to THEIR to-<side>/ inbox, not just an archived Response), push any unpushed commits ONLY after the suite is green (sole pusher, explicit pathspec), advance the mission/config/foundation work. If nothing is idle-and-unfed and nothing is unpushed, do nothing noisy — just confirm and go quiet." ;;
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
