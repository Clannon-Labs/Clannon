#!/usr/bin/env bash
# Read-only view of provider supervisor state.

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$ROOT/.agents/runtime"

printf 'Clannon provider state (%s):\n' "$(date '+%F %T %Z')"
for side in backend frontend memory orchestration security api; do
  state="$RUNTIME/$side.state"
  provider="$(sed -n 's/^provider=//p' "$state" 2>/dev/null | tail -n 1)"
  [ -n "$provider" ] || provider="not-started"
  printf '  %-14s %s' "$side" "$provider"
  for candidate in claude codex; do
    until_file="$RUNTIME/$side.$candidate.unavailable-until"
    until="$(cat "$until_file" 2>/dev/null || echo 0)"
    if [ "$until" -gt "$(date +%s)" ] 2>/dev/null; then
      printf ' | %s limited until %s' "$candidate" "$(date -d "@$until" '+%F %T %Z')"
    fi
  done
  printf '\n'
done
