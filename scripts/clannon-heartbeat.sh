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

# --- BACKEND idle-gating (owner policy 2026-07-06, refined) -----------------------
# React when ANY specialist goes idle — not only when both do — so an idle specialist
# gets its next INDEPENDENT task promptly instead of waiting on the other to finish.
# The timer polls often and cheaply; this gate nudges the coordinator only when a
# specialist has been idle long enough to be real (a dwell — so a mid-turn capture-pane
# flicker can't fire it) and only ONCE per that specialist's idle period. When nudged,
# the coordinator decides PER specialist: assign queued work that does NOT depend on
# what the OTHER specialist is still doing; if no safe independent work exists, leave it
# idle (never invent busywork). A specialist is "working" iff its tmux pane shows Claude
# Code's `esc to interrupt` hint (present only while a turn generates; a completed-turn
# summary line is not). A 20-min fallback still guarantees the coordinator is never stranded (owner: never idle).
if [ "$SIDE" = "backend" ]; then
  # If the coordinator itself is mid-turn, it needs no nudge — it'll finish and re-sweep.
  if tmux capture-pane -t "$SESSION" -p 2>/dev/null | grep -q "esc to interrupt"; then
    log "skip — coordinator is itself busy"
    exit 0
  fi

  LAST_PING="/tmp/clannon-heartbeat-backend.last-ping"  # unix ts of last nudge (fallback clock)
  FALLBACK_S=1200                                        # never let >20min pass with zero nudges (owner: never idle)
  DWELL_S=110                                            # a specialist's idle must PERSIST this long
                                                         # (>=2 consecutive polls) before it counts — a
                                                         # single flickered frame can't accumulate it.
  now="$(date +%s)"
  last="$(cat "$LAST_PING" 2>/dev/null || echo 0)"
  since=$(( now - last ))

  # Per-specialist state: <peer>.idle-since (first sustained-idle ts) and <peer>.handled
  # (already nudged-for THIS idle period). Both cleared the instant the peer works again,
  # so each fresh idle period is considered exactly once.
  need=""       # peers newly sustained-idle AND not yet considered -> a reason to nudge NOW
  idle_now=""   # peers currently sustained-idle -> all marked handled on a nudge
  for peer in memory orchestration; do
    SINCE="/tmp/clannon-hb-$peer.idle-since"
    HANDLED="/tmp/clannon-hb-$peer.handled"
    if tmux has-session -t "clannon-$peer" 2>/dev/null \
       && tmux capture-pane -t "clannon-$peer" -p 2>/dev/null | grep -q "esc to interrupt"; then
      rm -f "$SINCE" "$HANDLED"   # peer is working -> re-arm it
      continue
    fi
    # peer is idle this poll
    isince="$(cat "$SINCE" 2>/dev/null || echo 0)"
    if [ "$isince" -eq 0 ]; then echo "$now" > "$SINCE"; isince="$now"; fi
    [ $(( now - isince )) -lt "$DWELL_S" ] && continue   # not sustained yet — flicker guard
    idle_now="$idle_now $peer"
    [ -e "$HANDLED" ] || need="$need $peer"
  done

  # ROBUST COMMS (owner: NO proposal ever ignored). A pending proposal or owner reply sitting
  # in to-backend/ is unhandled work — nudge for it REGARDLESS of specialist-idle state, so a
  # MISSED proposal-wake (a systemd hiccup, or the coordinator was mid-turn when the path unit
  # fired and the keystroke didn't land) self-heals within one poll (~2 min) instead of waiting
  # for the fallback. Coordinator-busy is already skipped above, so this can't spam a working
  # coordinator; once the proposal is handled+archived it's gone, so it can't spam an idle one.
  pending=""
  for f in "$ROOT"/proposals/to-backend/*.md; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    case "$b" in CENTRAL_CONFIG.md|PHASE_BATCH_REDIS.md) continue ;; esac   # permanent owner briefs
    case "$(printf '%s' "$b" | tr '[:upper:]' '[:lower:]')" in reply*) pending="$b"; break ;; esac
    if grep -qiE '^Status:[[:space:]]*pending([[:space:]]|$)' "$f"; then pending="$b"; break; fi
  done

  reason=""
  if [ -n "$need" ]; then
    # A specialist became sustained-idle and hasn't been considered yet.
    for p in $idle_now; do : > "/tmp/clannon-hb-$p.handled"; done
    reason="idle:$need"
  fi
  [ -n "$pending" ] && reason="${reason:+$reason }pending-proposal:$pending"

  if [ -n "$reason" ]; then
    log "nudging coordinator — $reason (idle now:${idle_now:- none})"
  elif [ "$since" -ge "$FALLBACK_S" ]; then
    log "fallback nudge — nothing newly idle/pending but ${since}s since last (safety net)"
  else
    log "skip — nothing newly idle, no pending proposal"
    exit 0
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
    MSG="[COORDINATOR HEARTBEAT · a specialist is idle] A specialist went idle (or the 20-min safety tick). OWNER POLICY: the team NEVER sits idle — not a second wasted. If your live context is empty (fresh session) FIRST read docs/RESUME.md. Then: (1) capture-pane EVERY specialist (clannon-memory/orchestration + any you spawned) and for EACH idle one, assign its next INDEPENDENT task (one that won't collide with what another is mid-editing) via its to-<side>/ inbox — deliver rulings there, not just an archived Response; leave idle ONLY if it truly has no safe independent work. (2) check proposals/to-backend/ and push any unpushed commits after the suite is green (sole pusher, explicit pathspec). (3) THEN keep driving YOUR OWN remaining work (config-depth placements, D1 foundation moves, the mission) — do NOT go quiet while backend work remains; stop only when the whole backlog is empty for everyone." ;;
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
