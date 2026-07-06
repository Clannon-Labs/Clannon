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
# That single-frame read can FLICKER (a tool boundary / repaint mid-turn shows a frame
# without the hint), so a nudge additionally requires all-idle to PERSIST across polls
# (a dwell), never firing on one poll alone. A long fallback still guarantees the
# coordinator is never stranded asleep — even if a specialist builds for hours.
if [ "$SIDE" = "backend" ]; then
  # If the coordinator itself is mid-turn, it needs no nudge — it'll finish and re-sweep.
  if tmux capture-pane -t "$SESSION" -p 2>/dev/null | grep -q "esc to interrupt"; then
    log "skip — coordinator is itself busy"
    exit 0
  fi

  IDLE_STAMP="/tmp/clannon-heartbeat-backend.idle-pinged"  # set once nudged for the current idle period
  IDLE_SINCE="/tmp/clannon-heartbeat-backend.idle-since"   # unix ts we FIRST saw all-idle (cleared when any works)
  LAST_PING="/tmp/clannon-heartbeat-backend.last-ping"     # unix ts of last nudge (fallback clock)
  FALLBACK_S=3600                                          # never let >1h pass with zero nudges
  DWELL_S=110                                              # all-idle must PERSIST this long (≥2 consecutive polls)
                                                           # before a nudge, so a single flickered capture-pane
                                                           # frame (a tool boundary / repaint mid-turn) can't fire
                                                           # a false 'both idle' — the transient-idle false positive.
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
    # A specialist is building — reset BOTH idle markers so the next SUSTAINED all-idle
    # window starts fresh, and stay silent unless the 1h fallback has elapsed (safety net).
    rm -f "$IDLE_STAMP" "$IDLE_SINCE"
    if [ "$since" -lt "$FALLBACK_S" ]; then
      log "skip — busy:$working (idle-gated; ${since}s < ${FALLBACK_S}s fallback)"
      exit 0
    fi
    log "fallback nudge — busy:$working but ${since}s elapsed (safety net)"
  elif [ -e "$IDLE_STAMP" ]; then
    # Already nudged for this idle period — stay quiet until a specialist works again.
    log "skip — all idle but already nudged this idle period"
    exit 0
  else
    # All specialists idle THIS poll — require it to PERSIST across polls (dwell) before
    # nudging, so a one-frame flicker during a long turn can't trigger a false 'both idle'.
    idle_since="$(cat "$IDLE_SINCE" 2>/dev/null || echo 0)"
    if [ "$idle_since" -eq 0 ]; then
      echo "$now" > "$IDLE_SINCE"
      log "first all-idle poll — waiting ${DWELL_S}s to confirm it isn't a flicker"
      exit 0
    fi
    idle_for=$(( now - idle_since ))
    if [ "$idle_for" -lt "$DWELL_S" ]; then
      log "all idle ${idle_for}s — waiting for ${DWELL_S}s dwell before nudging"
      exit 0
    fi
    : > "$IDLE_STAMP"
    log "all specialists idle ${idle_for}s (>=${DWELL_S}s dwell) — nudging coordinator"
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
