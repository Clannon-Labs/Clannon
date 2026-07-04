#!/usr/bin/env bash
#
# proposal-wake.sh <backend|frontend> — wake one agent's tmux session because
# its proposal inbox changed. Fired by systemd --user (clannon-wake@<side>.path
# → clannon-wake@<side>.service) whenever proposals/to-<side>/ is modified.
#
# NEVER invokes claude / claude -p / any AI process. The only action is ONE
# `tmux send-keys` into the live interactive session the owner already runs.
#
# LOOP SAFETY (structural, not configured): each agent WRITES only to the
# OTHER side's inbox (backend → to-frontend/, frontend → to-backend/) and is
# WOKEN only by its OWN inbox. An agent handling a wake writes its Response
# into the file in its own inbox (not watched for the writer's side) and
# archives it to proposals/archive/ (not watched at all) — so handling a
# proposal can never re-trigger the sender or the handler. The 60s debounce
# below additionally absorbs any burst on one inbox.

set -uo pipefail   # deliberately no -e: every exit path below must be clean

SIDE="${1:?usage: proposal-wake.sh backend|frontend}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INBOX="$ROOT/proposals/to-$SIDE"
SESSION="clannon-$SIDE"
STAMP="/tmp/clannon-wake-$SIDE.stamp"
DEBOUNCE_S=60

log() { echo "clannon-wake[$SIDE]: $*"; }   # goes to the user journal

# Anything actually pending? Re-scan instead of trusting the event: dotfiles,
# editor swap/backup files (.swp, ~), and non-.md noise never count, and a
# directory event caused by ARCHIVING (a file moving OUT) finds no pending
# file and exits silently.
pending=0
for f in "$INBOX"/*.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  case "$base" in .*|*~|*.swp|*.swo) continue ;; esac
  pending=1; break
done
if [ "$pending" -eq 0 ]; then
  exit 0
fi

# Debounce: one wake per inbox per $DEBOUNCE_S window.
now="$(date +%s)"
if [ -f "$STAMP" ]; then
  last="$(cat "$STAMP" 2>/dev/null || echo 0)"
  if [ $((now - last)) -lt "$DEBOUNCE_S" ]; then
    log "debounced ($((now - last))s since last wake)"
    exit 0
  fi
fi

# Target session gone (agent not running)? Log once, exit clean — never error,
# never retry. The agent will find the file via its CLAUDE.md inbox check when
# it next starts.
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  log "session $SESSION not running — skipped (agent will catch it via inbox check)"
  exit 0
fi

echo "$now" > "$STAMP"
MSG="[auto-wake] New proposal in your inbox — read the pending file(s) in proposals/to-$SIDE/, handle per the Proposal Protocol in CLAUDE.md, respond in the proposal file, and archive when done."
# The TEXT goes in one send-keys call so it lands as one message. Enter is sent
# SEPARATELY after a beat: Claude Code's TUI reads a text+Enter burst as one
# stdin chunk and treats it as a PASTE (inserts a newline instead of
# submitting) — verified live 2026-07-04; a detached Enter is a real keypress
# and submits.
tmux send-keys -t "$SESSION" "$MSG"
sleep 0.5
tmux send-keys -t "$SESSION" Enter
log "woke $SESSION"
