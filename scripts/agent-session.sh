#!/usr/bin/env bash
#
# agent-session.sh — start (or attach to) one Clannon agent session.
#
#   ./scripts/agent-session.sh backend        → "clannon-backend",       cwd repo root
#   ./scripts/agent-session.sh frontend       → "clannon-frontend",      cwd frontend/
#   ./scripts/agent-session.sh memory         → "clannon-memory",        cwd backend/core/memory/
#   ./scripts/agent-session.sh orchestration  → "clannon-orchestration", cwd backend/core/orchestrator/
#   ./scripts/agent-session.sh security       → "clannon-security",      cwd backend/security/
#   ./scripts/agent-session.sh api            → "clannon-api",           cwd backend/api/
#
# This remains attach/create-only. To launch provider failover use:
#   ./scripts/clannon-standup.sh dual [side...]
#
# backend/frontend are the two peer agents; memory/orchestration/security/api are
# backend SPECIALISTS the backend agent coordinates (their charters live in the
# CLAUDE.md of their home dir). The wake system (clannon-wake@<side>.path) injects
# "[auto-wake] ..." into these EXACT session names with tmux send-keys — Claude
# Code must be running INSIDE these sessions for cross-agent wake to work. Start
# claude yourself after attaching; this script never invokes claude.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

side="${1:-}"
case "$side" in
  backend)       session="clannon-backend";       dir="$ROOT" ;;
  frontend)      session="clannon-frontend";      dir="$ROOT/frontend" ;;
  memory)        session="clannon-memory";        dir="$ROOT/backend/core/memory" ;;
  orchestration) session="clannon-orchestration"; dir="$ROOT/backend/core/orchestrator" ;;
  security)      session="clannon-security";      dir="$ROOT/backend/security" ;;
  api)           session="clannon-api";           dir="$ROOT/backend/api" ;;
  *) echo "usage: $0 backend|frontend|memory|orchestration|security|api" >&2; exit 2 ;;
esac

# -A: attach if it exists, create if not — idempotent either way.
exec tmux new-session -A -s "$session" -c "$dir"
