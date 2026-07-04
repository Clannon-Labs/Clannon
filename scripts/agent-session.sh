#!/usr/bin/env bash
#
# agent-session.sh — start (or attach to) one of the two Clannon agent sessions.
#
#   ./scripts/agent-session.sh backend    → tmux session "clannon-backend", cwd repo root
#   ./scripts/agent-session.sh frontend   → tmux session "clannon-frontend", cwd frontend/
#
# The wake system (clannon-wake@*.path) injects "[auto-wake] ..." messages into
# these EXACT session names with tmux send-keys — Claude Code must be running
# INSIDE these sessions for cross-agent wake to work. Start claude yourself
# after attaching; this script never invokes claude.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

side="${1:-}"
case "$side" in
  backend)  session="clannon-backend";  dir="$ROOT" ;;
  frontend) session="clannon-frontend"; dir="$ROOT/frontend" ;;
  *) echo "usage: $0 backend|frontend" >&2; exit 2 ;;
esac

# -A: attach if it exists, create if not — idempotent either way.
exec tmux new-session -A -s "$session" -c "$dir"
