#!/usr/bin/env bash
#
# One-command backend launcher for LAN dev (phone testing).
# Run from anywhere:  ./dev.sh   (or  bash dev.sh)
#
# Idempotent: frees port 8000 first, so re-running never hits
# "address already in use" from a previous run still hanging around.
# No env vars to remember — the LAN IP is detected and CORS is wired for it.

set -euo pipefail
cd "$(dirname "$0")"   # always run from backend/, regardless of caller's cwd

PORT=8000

# Free $PORT by killing whatever is LISTENing on it, plus its process group so
# supervisor parents (uvicorn --reload, npm) die too and can't re-grab the port.
# Uses ss, not `lsof -i` — lsof also matches transient *client* connections and
# would kill the wrong PIDs while the real listener survives.
free_port() {
  local port="$1" self_pgid pids pid pgid i
  self_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
  pids="$(ss -ltnpH "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u || true)"
  [ -z "$pids" ] && return 0
  echo "› freeing port $port (stale process from a previous run)…"
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

if [ ! -x .venv/bin/uvicorn ]; then
  echo "✗ .venv/bin/uvicorn not found — create the venv and install deps first." >&2
  exit 1
fi

echo "› backend  → http://$LAN_IP:$PORT   (CORS origin http://$LAN_IP:3000)"
export FRONTEND_ORIGIN="http://$LAN_IP:3000"
exec .venv/bin/uvicorn api.app:app --host 0.0.0.0 --port "$PORT" --reload
