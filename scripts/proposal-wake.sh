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
# file and exits silently. Track the NEWEST pending file — it is the one that
# just triggered us, and its optional `Wake:` line drives the typed message.
newest=""
for f in "$INBOX"/*.md; do
  [ -e "$f" ] || continue
  base="$(basename "$f")"
  case "$base" in .*|*~|*.swp|*.swo) continue ;; esac
  # A file wakes the agent if EITHER:
  #  (1) its name starts with `reply` (case-insensitive) — the OWNER's reply-drop
  #      convention. The owner answers a report by dropping a `reply*.md` here; it
  #      is a bare answer, not a formatted proposal, so it has no `Status:` header
  #      and would otherwise be missed (this is exactly the gap that let a dropped
  #      reply sit unseen until the next heartbeat — fixed 2026-07-06). Handling it
  #      = archiving it OUT of this inbox, which re-fires the path unit but finds no
  #      reply*/pending file, so it can never self-loop.
  #  (2) OR it is a PENDING proposal (an agent's normal proposal). This is what
  #      prevents a SELF-WAKE: when the receiving agent edits a file in its own
  #      inbox to respond (flip Status to accepted/rejected/done, append its
  #      Response), that write re-fires this path unit — but the file is no longer
  #      `pending`, so it is skipped. It also skips settled reference files (owner
  #      briefs) and absorbs partial-write races (a half-written file has no Status
  #      line yet, so it waits for the complete write).
  case "$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')" in
    reply*) : ;;   # owner reply drop — always wakes, no header needed
    *) grep -qiE '^Status:[[:space:]]*pending([[:space:]]|$)' "$f" || continue ;;
  esac
  if [ -z "$newest" ] || [ "$f" -nt "$newest" ]; then
    newest="$f"
  fi
done
if [ -z "$newest" ]; then
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

# The sender may author the ping: a single-line `Wake:` header in the proposal
# becomes the typed message (prefixed with [auto-wake] so the recipient still
# recognizes it as a system ping and runs its inbox check per CLAUDE.md). No
# `Wake:` line ⇒ the generic default. One line only — richer detail belongs in
# the proposal body, which the recipient reads anyway. \r stripped (CRLF files).
custom="$(grep -m1 -oP '^Wake:\s*\K.*' "$newest" 2>/dev/null | tr -d '\r' || true)"
# Name the SENDER in the wake itself (from the proposal's `From:` header) so the
# recipient never has to infer who pinged it. Falls back to a bare tag if absent.
sender="$(grep -m1 -oP '^From:\s*\K\S+' "$newest" 2>/dev/null | tr -d '\r' || true)"
tag="[auto-wake${sender:+ from $sender}]"
if [ -n "$custom" ]; then
  MSG="$tag $custom"
else
  MSG="$tag New proposal in your inbox — read the pending file(s) in proposals/to-$SIDE/, handle per the Proposal Protocol in CLAUDE.md, respond in the proposal file, and archive when done."
fi

# The TEXT goes in one send-keys call so it lands as one message; `-l` types it
# LITERALLY so an author-written message can never be misread as a tmux key name
# (e.g. a bare "Enter" or "C-c"). Enter is sent SEPARATELY after a beat: Claude
# Code's TUI reads a text+Enter burst as one stdin chunk and treats it as a
# PASTE (inserts a newline instead of submitting) — verified live 2026-07-04; a
# detached Enter is a real keypress and submits.
tmux send-keys -t "$SESSION" -l "$MSG"
sleep 0.5
tmux send-keys -t "$SESSION" Enter
log "woke $SESSION (custom=${custom:+yes})"
