#!/usr/bin/env bash
#
# One-command frontend launcher for LAN dev (phone testing).
# Run from anywhere:  ./dev.sh   (or  npm run lan)
#
# Idempotent: frees port 3000 first, so re-running never hits Next's
# "Another next dev server is already running" / port-3001 fallback.
# The LAN IP is detected and the browser-side API + CORS origin are wired
# for it — the phone runs the fetch, so it must hit the LAN IP, not localhost.

set -euo pipefail
cd "$(dirname "$0")"   # always run from frontend/, regardless of caller's cwd

PORT=3000

# Free $PORT by killing whatever is LISTENing on it, plus its process group so
# the whole `next dev` tree (npm → next → next-server → workers) dies and can't
# re-grab the port. Uses ss, not `lsof -i` — lsof also matches transient
# *client* connections and would kill the wrong PIDs while the listener lives.
free_port() {
  local port="$1" self_pgid pids pid pgid i
  self_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
  pids="$(ss -ltnpH "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u || true)"
  [ -z "$pids" ] && return 0
  echo "› freeing port $port (stale dev server from a previous run)…"
  for pid in $pids; do
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [ -n "$pgid" ] && [ "$pgid" -gt 1 ] 2>/dev/null && [ "$pgid" != "$self_pgid" ]; then
      kill -9 "-$pgid" 2>/dev/null || true
    fi
    kill -9 "$pid" 2>/dev/null || true
  done
  for i in 1 2 3 4 5 6; do            # wait up to ~3s for the kernel to release it
    ss -ltnH "sport = :$port" 2>/dev/null | grep -q . || return 0
    sleep 0.5
  done
}

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LAN_IP="${LAN_IP:-127.0.0.1}"

free_port "$PORT"

echo "› frontend → http://$LAN_IP:$PORT   (API http://$LAN_IP:8000)"
export NEXT_PUBLIC_API_MODE=http
export NEXT_PUBLIC_API_BASE_URL="http://$LAN_IP:8000"
export NEXT_PUBLIC_SITE_URL="http://$LAN_IP:$PORT"
exec npm run dev -- -H 0.0.0.0 -p "$PORT"
