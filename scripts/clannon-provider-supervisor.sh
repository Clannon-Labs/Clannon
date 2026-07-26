#!/usr/bin/env bash
#
# Keep one Clannon role alive across Claude Code and Codex subscription limits.
#
# Claude always gets first choice. A provider is switched only when a known
# usage-limit message remains visible for five continuous minutes. Provider
# conversation stores are incompatible, so cross-provider continuity comes from
# repository context + the shared provider handoff, never from pretending one
# CLI can resume the other's private session.

set -uo pipefail
# Resume failure is control flow: callers must not make it fatal via SHELLOPTS.
set +e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIDE="${1:?usage: clannon-provider-supervisor.sh backend|frontend|memory|orchestration|security|api}"
MODE="${2:-resume}"
CONFIRM_S=300
POLL_S=15

case "$SIDE" in
  backend)
    ROLE_DIR="$ROOT"; ROLE_HANDOFF=".claude/contexts/HANDOFF.md"
    ROLE_INBOXES="$ROOT/proposals/to-backend/ and $ROOT/backend/proposals/"
    ;;
  frontend)
    ROLE_DIR="$ROOT/frontend"; ROLE_HANDOFF="HANDOFF.md"
    ROLE_INBOXES="$ROOT/proposals/to-frontend/ and $ROOT/frontend/proposals/"
    ;;
  memory)
    ROLE_DIR="$ROOT/backend/core/memory"; ROLE_HANDOFF="HANDOFF_batch.md"
    ROLE_INBOXES="$ROOT/proposals/to-memory/"
    ;;
  orchestration)
    ROLE_DIR="$ROOT/backend/core/orchestrator"; ROLE_HANDOFF="HANDOFF_mission.md"
    ROLE_INBOXES="$ROOT/proposals/to-orchestration/"
    ;;
  security)
    ROLE_DIR="$ROOT/backend/security"; ROLE_HANDOFF="HANDOFF_security.md"
    ROLE_INBOXES="$ROOT/proposals/to-security/"
    ;;
  api)
    ROLE_DIR="$ROOT/backend/api"; ROLE_HANDOFF="HANDOFF_api.md"
    ROLE_INBOXES="$ROOT/proposals/to-api/"
    ;;
  *) echo "usage: $0 backend|frontend|memory|orchestration|security|api [resume|fresh]" >&2; exit 2 ;;
esac
case "$MODE" in resume|fresh) ;; *) echo "mode must be resume or fresh" >&2; exit 2 ;; esac

RUNTIME_DIR="${CLANNON_PROVIDER_RUNTIME_DIR:-$ROOT/.agents/runtime}"
HANDOFF_DIR="$ROOT/.agents/provider-handoffs"
STATE_FILE="$RUNTIME_DIR/$SIDE.state"
COMMON_HANDOFF="$HANDOFF_DIR/$SIDE.md"
if ! mkdir -p "$RUNTIME_DIR" "$HANDOFF_DIR"; then
  echo "clannon-provider[$SIDE]: cannot create runtime/handoff directory" >&2
  exit 1
fi
runtime_probe="$RUNTIME_DIR/.writable.$$"
if ! : > "$runtime_probe"; then
  echo "clannon-provider[$SIDE]: runtime directory is not writable: $RUNTIME_DIR" >&2
  echo "Set CLANNON_PROVIDER_RUNTIME_DIR to a writable private directory." >&2
  exit 1
fi
rm -f "$runtime_probe"

log() { echo "clannon-provider[$SIDE]: $*"; }

ensure_handoff() {
  [ -f "$COMMON_HANDOFF" ] && return 0
  {
    echo "# Shared provider handoff — $SIDE"
    echo
    echo "This file transfers live work between Claude Code and Codex. Update before"
    echo "planned exits, compaction, or provider switches."
    echo
    echo "## Current checkpoint"
    echo
    echo "- Provider: not recorded"
    echo "- Updated: not recorded"
    echo "- Task: read role handoff and inbox"
    echo "- State: no provider checkpoint yet"
    echo "- Next: resume from durable role context"
    echo "- Files touched: none recorded"
    echo "- Verification: none recorded"
    echo
    echo "## Change note"
    echo
    echo "Created by provider supervisor. No earlier shared-provider checkpoint existed."
    echo
    echo "## Previous checkpoint"
    echo
    echo "None."
  } > "$COMMON_HANDOFF"
}

write_state() {
  local provider="$1" claude_until="$2" codex_until="$3"
  {
    echo "provider=$provider"
    echo "claude_until=$claude_until"
    echo "codex_until=$codex_until"
  } > "$STATE_FILE"
}

read_state_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$STATE_FILE" 2>/dev/null | tail -n 1
}

limit_pattern() {
  case "$1" in
    claude)
      printf '%s' "You've hit your session limit|hit your session limit|usage limit.*reset|upgrade to increase your usage limit"
      ;;
    codex)
      printf '%s' "You've hit.*(usage|session).*limit|usage limit.*reset|rate limit.*reset|quota exceeded|usage_limit_reached|insufficient_quota"
      ;;
  esac
}

pane_has_limit() {
  local provider="$1" pane="${TMUX_PANE:-}"
  [ -n "$pane" ] || return 1
  tmux capture-pane -t "$pane" -p -S -160 2>/dev/null |
    grep -qiE "$(limit_pattern "$provider")"
}

parse_reset_epoch() {
  local provider="$1" pane="${TMUX_PANE:-}" line clock epoch now
  [ -n "$pane" ] || return 1
  line="$(
    tmux capture-pane -t "$pane" -p -S -160 2>/dev/null |
      grep -iE "$(limit_pattern "$provider")" |
      tail -n 1
  )"
  clock="$(printf '%s\n' "$line" | grep -ioE 'resets[[:space:]]+[0-9]{1,2}:[0-9]{2}[[:space:]]*(am|pm)' | head -n 1 | sed -E 's/^resets[[:space:]]+//I')"
  [ -n "$clock" ] || return 1
  epoch="$(date -d "today $clock" +%s 2>/dev/null)" || return 1
  now="$(date +%s)"
  [ "$epoch" -gt "$now" ] || epoch="$(date -d "tomorrow $clock" +%s 2>/dev/null)" || return 1
  printf '%s\n' "$epoch"
}

startup_prompt() {
  cat <<EOF
[provider-resume · $SIDE] Continue existing Clannon role; do not restart work.
Read completely before acting:
1. role instructions (CLAUDE.md and AGENTS.md from repo root through current directory);
2. durable role handoff: $ROLE_HANDOFF;
3. shared cross-provider handoff: $COMMON_HANDOFF;
4. role inbox(es): $ROLE_INBOXES;
5. latest role report, docs/RESUME.md when applicable, and git status/diff.

Claude Code and Codex share files, not private conversation history. Treat shared
handoff as latest live checkpoint. Before compaction, planned exit, or suspected
context exhaustion, update it atomically. Preserve prior checkpoint under
"Previous checkpoint" and explain what changed under "Change note" so another
provider can audit or roll back reasoning.

Never ask owner through popup/session. Specialists route decisions to backend via
proposal files. Anything requiring owner decision becomes clearly named
reports/REPLY_NEEDED_<slug>.md; continue independent work instead of waiting.
Stay inside role ownership boundary. Do not overwrite another agent's dirty work.
EOF
}

launch_provider() {
  local provider="$1" prompt="$2"
  cd "$ROLE_DIR" || return 1
  case "$provider" in
    claude)
      local -a cmd=(claude --permission-mode dontAsk --name "clannon-$SIDE")
      case "$SIDE" in memory|orchestration|security|api) cmd+=(--model claude-sonnet-5) ;; esac
      # Resume latest role-local conversation whenever one exists.
      cmd+=(--continue "$prompt")
      "${cmd[@]}"
      ;;
    codex)
      # Workspace-write + never-ask: unattended without bypassing sandbox.
      codex resume --last -C "$ROLE_DIR" --add-dir "$ROOT" \
        --sandbox workspace-write --ask-for-approval never "$prompt"
      ;;
  esac
}

launch_fresh_provider() {
  local provider="$1" prompt="$2"
  cd "$ROLE_DIR" || return 1
  case "$provider" in
    claude)
      local -a cmd=(claude --permission-mode dontAsk --name "clannon-$SIDE")
      case "$SIDE" in memory|orchestration|security|api) cmd+=(--model claude-sonnet-5) ;; esac
      cmd+=("$prompt")
      "${cmd[@]}"
      ;;
    codex)
      codex -C "$ROLE_DIR" --add-dir "$ROOT" \
        --sandbox workspace-write --ask-for-approval never "$prompt"
      ;;
  esac
}

monitor_limit() {
  local provider="$1" active_file="$2" switch_file="$3" first_seen=0 now reset_epoch
  while [ -e "$active_file" ]; do
    if pane_has_limit "$provider"; then
      now="$(date +%s)"
      [ "$first_seen" -ne 0 ] || {
        first_seen="$now"
        log "$provider limit text seen; confirming for ${CONFIRM_S}s"
      }
      if [ $((now - first_seen)) -ge "$CONFIRM_S" ]; then
        reset_epoch="$(parse_reset_epoch "$provider" 2>/dev/null || true)"
        [ -n "$reset_epoch" ] || reset_epoch=$((now + CONFIRM_S))
        printf '%s\n' "$reset_epoch" > "$RUNTIME_DIR/$SIDE.$provider.unavailable-until"
        log "$provider limit confirmed; checkpoint file is $COMMON_HANDOFF"
        printf '%s\n' "$provider" > "$switch_file"
        tmux send-keys -t "${TMUX_PANE}" C-c 2>/dev/null || true
        sleep 2
        tmux send-keys -t "${TMUX_PANE}" -l "/exit" 2>/dev/null || true
        sleep 0.5
        tmux send-keys -t "${TMUX_PANE}" Enter 2>/dev/null || true
        return 0
      fi
    else
      first_seen=0
    fi
    sleep "$POLL_S"
  done
  return 0
}

provider_available_at() {
  local provider="$1"
  local file="$RUNTIME_DIR/$SIDE.$provider.unavailable-until"
  cat "$file" 2>/dev/null || echo 0
}

choose_provider() {
  local now claude_at codex_at
  now="$(date +%s)"
  claude_at="$(provider_available_at claude)"
  codex_at="$(provider_available_at codex)"
  if [ "$claude_at" -le "$now" ]; then echo claude
  elif [ "$codex_at" -le "$now" ]; then echo codex
  elif [ "$claude_at" -le "$codex_at" ]; then echo "wait:claude:$claude_at"
  else echo "wait:codex:$codex_at"
  fi
}

ensure_handoff
provider="$(read_state_value provider)"
[ "$provider" = claude ] || [ "$provider" = codex ] || provider=claude
fresh_next=""

while true; do
  choice="$(choose_provider)"
  case "$choice" in
    wait:*)
      provider="${choice#wait:}"; provider="${provider%%:*}"
      until_epoch="${choice##*:}"
      wait_s=$((until_epoch - $(date +%s)))
      [ "$wait_s" -gt 0 ] || wait_s=1
      log "both providers limited; waiting ${wait_s}s for $provider"
      sleep "$wait_s"
      ;;
    *) provider="$choice" ;;
  esac

  write_state "$provider" "$(provider_available_at claude)" "$(provider_available_at codex)"
  log "starting $provider; latest saved $provider session requested"

  # Clear prior provider's visible limit text so it cannot trip new provider.
  if [ -n "${TMUX_PANE:-}" ]; then
    tmux clear-history -t "$TMUX_PANE" 2>/dev/null || true
    tmux send-keys -t "$TMUX_PANE" C-l 2>/dev/null || true
  fi

  prompt="$(startup_prompt)"
  start="$(date +%s)"
  active_file="$RUNTIME_DIR/$SIDE.monitor-active.$$"
  switch_file="$RUNTIME_DIR/$SIDE.switch.$$"
  : > "$active_file"
  rm -f "$switch_file"
  monitor_limit "$provider" "$active_file" "$switch_file" &
  monitor=$!
  # Provider must remain foreground. Interactive TUIs lose terminal input when
  # launched as background jobs by a non-interactive shell.
  was_fresh=0
  if [ "$fresh_next" = "$provider" ]; then
    fresh_next=""
    was_fresh=1
    if launch_fresh_provider "$provider" "$prompt"; then
      rc=0
    else
      rc=$?
    fi
  else
    if launch_provider "$provider" "$prompt"; then
      rc=0
    else
      rc=$?
    fi
  fi
  rm -f "$active_file"

  # Some CLI builds print a hard usage-limit error and exit immediately instead
  # of leaving the TUI open. Process exit is already conclusive failure, so the
  # five-minute "maybe still generating" dwell is unnecessary in this path.
  # Record reset/cooldown before clearing the pane, then let normal switch logic
  # start the other provider.
  if [ "$rc" -ne 0 ] && pane_has_limit "$provider"; then
    reset_epoch="$(parse_reset_epoch "$provider" 2>/dev/null || true)"
    [ -n "$reset_epoch" ] || reset_epoch=$(( $(date +%s) + CONFIRM_S ))
    printf '%s\n' "$reset_epoch" > "$RUNTIME_DIR/$SIDE.$provider.unavailable-until"
    printf '%s\n' "$provider" > "$switch_file"
    log "$provider exited with confirmed usage-limit text; switching provider"
  fi

  kill "$monitor" 2>/dev/null || true
  wait "$monitor" 2>/dev/null || true

  if [ -e "$switch_file" ]; then
    rm -f "$switch_file"
    [ "$provider" = claude ] && provider=codex || provider=claude
    continue
  fi

  elapsed=$(( $(date +%s) - start ))
  if [ "$rc" -ne 0 ] && [ "$elapsed" -lt 15 ] && [ "$was_fresh" -eq 0 ]; then
    log "$provider had no resumable session or failed during resume; next attempt will be fresh"
    fresh_next="$provider"
    continue
  fi

  log "$provider exited without a confirmed usage limit (status $rc); not switching silently"
  exit "$rc"
done
