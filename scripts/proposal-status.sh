#!/usr/bin/env bash
#
# proposal-status.sh — print pending cross-agent / owner proposals per inbox.
# Owner convenience only: no watchers, no daemons, no claude invocations.
# The agents themselves check their inboxes per the CLAUDE.md Proposal Protocol.

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root, regardless of caller's cwd

show_inbox() {
  local label="$1" dir="$2" found=0
  [ -d "$dir" ] || return 0
  for f in "$dir"/*.md; do
    [ -e "$f" ] || continue
    local status priority summary
    status="$(grep -m1 -oP '^Status:\s*\K\S+' "$f" 2>/dev/null || echo '?')"
    [ "$status" = "done" ] || [ "$status" = "rejected" ] && continue
    priority="$(grep -m1 -oP '^Priority:\s*\K\S+' "$f" 2>/dev/null || echo '?')"
    summary="$(grep -m1 -oP '^Summary:\s*\K.*' "$f" 2>/dev/null || echo '(no summary)')"
    if [ "$found" -eq 0 ]; then echo "── $label"; found=1; fi
    printf '   [%s/%s] %s — %s\n' "$status" "$priority" "$(basename "$f")" "$summary"
  done
  return 0
}

echo "Pending proposals ($(date +%F)):"
show_inbox "to BACKEND agent   (proposals/to-backend/)"   "proposals/to-backend"
show_inbox "to BACKEND agent   (backend/proposals/)"      "backend/proposals"
show_inbox "to FRONTEND agent  (proposals/to-frontend/)"  "proposals/to-frontend"
show_inbox "to FRONTEND agent  (frontend/proposals/)"     "frontend/proposals"
echo "(done/rejected live in proposals/archive/; format: proposals/README.md)"
