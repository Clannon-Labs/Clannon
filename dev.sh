#!/usr/bin/env bash
#
# Canonical Clannon development launcher.
#
# Browser traffic uses one origin:
#   http://<host>:3000          Next.js
#   http://<host>:3000/api/*    proxied by Next.js to FastAPI on 127.0.0.1:8000
#
# ClamAV and Qdrant are reused when already listening. Otherwise this script
# starts persistent local containers with Docker or Podman.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# core.hooksPath is local config and so cannot be tracked; installing it from the
# two entry points everyone already runs is what stops commit-identity
# enforcement from being "enabled on whichever machine remembered".
"$ROOT_DIR/scripts/setup-hooks.sh" || true

FRONTEND_PORT="${CLANNON_FRONTEND_PORT:-3000}"
BACKEND_PORT="${CLANNON_BACKEND_PORT:-8000}"
CLAMAV_PORT="${CLAMAV_PORT:-3310}"
QDRANT_PORT="${CLANNON_QDRANT_PORT:-6333}"
SERVICE_WAIT_SECONDS="${CLANNON_SERVICE_WAIT_SECONDS:-180}"

BACKEND_PID=""
FRONTEND_PID=""

usage() {
  cat <<'EOF'
Usage: ./dev.sh

Starts full local Clannon stack:
  - ClamAV and Qdrant (existing listeners, or Docker/Podman containers)
  - FastAPI backend on private port 8000
  - Next.js frontend on public port 3000
  - /api/* reverse proxy from Next.js to FastAPI

Optional environment:
  CLANNON_FRONTEND_PORT=3000
  CLANNON_BACKEND_PORT=8000
  CLANNON_QDRANT_PORT=6333
  CLANNON_SERVICE_WAIT_SECONDS=180
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi
if [ "$#" -ne 0 ]; then
  usage >&2
  exit 2
fi

fail() {
  echo "✗ $*" >&2
  exit 1
}

command -v ss >/dev/null 2>&1 || fail "'ss' is required to inspect local ports."
command -v curl >/dev/null 2>&1 || fail "'curl' is required for readiness checks."
[ -x "$BACKEND_DIR/.venv/bin/uvicorn" ] ||
  fail "backend/.venv/bin/uvicorn missing. Install backend dependencies first."
[ -d "$FRONTEND_DIR/node_modules" ] ||
  fail "frontend/node_modules missing. Run: cd frontend && npm install"

port_is_open() {
  ss -ltnH "sport = :$1" 2>/dev/null | grep -q .
}

listener_pids() {
  ss -ltnpH "sport = :$1" 2>/dev/null |
    grep -oE 'pid=[0-9]+' |
    cut -d= -f2 |
    sort -u
}

# Replace only Clannon-owned stale listeners. Never kill an unrelated process
# merely because it happens to occupy a conventional development port.
clear_clannon_port() {
  local port="$1" label="$2" pid cwd pgid self_pgid
  local -a pids=()
  mapfile -t pids < <(listener_pids "$port")
  [ "${#pids[@]}" -eq 0 ] && return 0

  for pid in "${pids[@]}"; do
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    case "$cwd" in
      "$ROOT_DIR"|"$ROOT_DIR"/*) ;;
      *) fail "port $port is occupied by non-Clannon PID $pid ($cwd). Stop it, then rerun ./dev.sh." ;;
    esac
  done

  echo "› replacing stale Clannon $label on port $port"
  self_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
  for pid in "${pids[@]}"; do
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [ -n "$pgid" ] && [ "$pgid" -gt 1 ] 2>/dev/null && [ "$pgid" != "$self_pgid" ]; then
      kill -TERM -- "-$pgid" 2>/dev/null || true
    else
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  for _ in {1..20}; do
    port_is_open "$port" || return 0
    sleep 0.25
  done

  # Reload supervisors can take longer than ordinary children to drain. The
  # target was ownership-checked above; after a graceful window, force only
  # remaining listeners on this exact Clannon port to exit.
  mapfile -t pids < <(listener_pids "$port")
  for pid in "${pids[@]}"; do
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    case "$cwd" in
      "$ROOT_DIR"|"$ROOT_DIR"/*) kill -KILL "$pid" 2>/dev/null || true ;;
      *) fail "port $port changed ownership to PID $pid ($cwd); refusing to kill it." ;;
    esac
  done
  for _ in {1..20}; do
    port_is_open "$port" || return 0
    sleep 0.25
  done
  fail "Clannon $label did not release port $port."
}

container_engine() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo docker
    return
  fi
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    echo podman
    return
  fi
  return 1
}

ensure_container() {
  local engine="$1" name="$2"
  shift 2
  if "$engine" container inspect "$name" >/dev/null 2>&1; then
    if [ "$("$engine" inspect -f '{{.State.Running}}' "$name")" != "true" ]; then
      echo "› starting $name"
      "$engine" start "$name" >/dev/null
    fi
    return
  fi
  echo "› creating $name"
  "$engine" run -d --name "$name" --restart unless-stopped "$@" >/dev/null
}

start_services() {
  local need_clamav=0 need_qdrant=0 engine
  port_is_open "$CLAMAV_PORT" || need_clamav=1
  port_is_open "$QDRANT_PORT" || need_qdrant=1
  [ "$need_clamav" -eq 0 ] && [ "$need_qdrant" -eq 0 ] && return

  engine="$(container_engine)" ||
    fail "ClamAV/Qdrant unavailable and no working Docker or Podman engine found."

  if [ "$need_clamav" -eq 1 ]; then
    ensure_container "$engine" clannon-dev-clamav \
      -p "127.0.0.1:$CLAMAV_PORT:3310" \
      -v clannon-dev-clamav-data:/var/lib/clamav \
      docker.io/clamav/clamav:latest
  fi
  if [ "$need_qdrant" -eq 1 ]; then
    ensure_container "$engine" clannon-dev-qdrant \
      -p "127.0.0.1:$QDRANT_PORT:6333" \
      -v clannon-dev-qdrant-data:/qdrant/storage \
      docker.io/qdrant/qdrant:latest
  fi
}

clamav_is_ready() {
  "$BACKEND_DIR/.venv/bin/python" -c '
import socket
s = socket.create_connection(("127.0.0.1", int(__import__("sys").argv[1])), timeout=1)
s.sendall(b"zPING\0")
reply = s.recv(16)
s.close()
raise SystemExit(0 if reply.rstrip(b"\0") == b"PONG" else 1)
' "$CLAMAV_PORT" >/dev/null 2>&1
}

wait_for_services() {
  local deadline=$((SECONDS + SERVICE_WAIT_SECONDS))
  echo "› waiting for ClamAV and Qdrant"
  while (( SECONDS < deadline )); do
    if clamav_is_ready &&
      curl -fsS --max-time 1 "http://127.0.0.1:$QDRANT_PORT/readyz" >/dev/null 2>&1; then
      echo "✓ services ready"
      return
    fi
    sleep 1
  done
  fail "services not ready after ${SERVICE_WAIT_SECONDS}s (ClamAV 127.0.0.1:$CLAMAV_PORT, Qdrant 127.0.0.1:$QDRANT_PORT)."
}

wait_for_http() {
  local url="$1" label="$2" pid="$3" deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    kill -0 "$pid" 2>/dev/null || fail "$label exited during startup."
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      return
    fi
    sleep 0.5
  done
  fail "$label did not become ready at $url."
}

terminate_group() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM HUP
  terminate_group "$FRONTEND_PID"
  terminate_group "$BACKEND_PID"
  wait "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
LAN_IP="${LAN_IP:-127.0.0.1}"
PUBLIC_ORIGIN="http://$LAN_IP:$FRONTEND_PORT"
INTERNAL_API="http://127.0.0.1:$BACKEND_PORT"

clear_clannon_port "$BACKEND_PORT" backend
clear_clannon_port "$FRONTEND_PORT" frontend
start_services
wait_for_services

mkdir -p "$BACKEND_DIR/assets/fastembed_cache"

echo "› backend  → $INTERNAL_API (private; proxied at $PUBLIC_ORIGIN/api)"
(
  cd "$BACKEND_DIR"
  exec setsid env \
    FRONTEND_ORIGIN="$PUBLIC_ORIGIN" \
    SERVER_CORS_ORIGINS="$PUBLIC_ORIGIN" \
    CLAMAV_HOST=127.0.0.1 \
    CLAMAV_PORT="$CLAMAV_PORT" \
    QDRANT_URL="http://127.0.0.1:$QDRANT_PORT" \
    VRAKSHA_EMBED_CACHE="$BACKEND_DIR/assets/fastembed_cache" \
    .venv/bin/uvicorn api.app:app \
      --host 127.0.0.1 \
      --port "$BACKEND_PORT" \
      --reload
) &
BACKEND_PID=$!
wait_for_http "$INTERNAL_API/health" backend "$BACKEND_PID"

echo "› frontend → $PUBLIC_ORIGIN"
(
  cd "$FRONTEND_DIR"
  exec setsid env \
    NEXT_PUBLIC_API_MODE=http \
    NEXT_PUBLIC_API_BASE_URL="$PUBLIC_ORIGIN/api" \
    NEXT_PUBLIC_SITE_URL="$PUBLIC_ORIGIN" \
    CLANNON_DEV_BACKEND_URL="$INTERNAL_API" \
    npm run dev -- --hostname 0.0.0.0 --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!
wait_for_http "$PUBLIC_ORIGIN" frontend "$FRONTEND_PID"

echo "✓ Clannon ready: $PUBLIC_ORIGIN"
echo "  API through same origin: $PUBLIC_ORIGIN/api"
echo "  Ctrl-C stops frontend/backend; service containers remain warm."

set +e
wait -n "$BACKEND_PID" "$FRONTEND_PID"
status=$?
set -e
if [ "$status" -eq 130 ] || [ "$status" -eq 143 ]; then
  exit 0
fi
echo "✗ development process exited (status $status)" >&2
exit "$status"
