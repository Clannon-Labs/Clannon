#!/usr/bin/env bash
# Enforced launcher for the independent backend security auditor.
#
# Source tree is mounted read-only. Only auditor-owned evidence/continuity paths
# and isolated Codex runtime state are writable. Prompt instructions are not the
# security boundary; Bubblewrap is. Missing Bubblewrap therefore fails closed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROLE_DIR="$ROOT/backend-audit"
RUNTIME="${CLANNON_AUDIT_RUNTIME:-$ROOT/.agents/runtime/backend-audit}"
CODEX_STATE="$RUNTIME/codex-home"
TOOLS_VENV="$RUNTIME/tools-venv"
REPORTS="$ROOT/reports/backend-audit"
PROPOSALS="$ROOT/proposals/to-backend/from-backend-audit"
TODAY="$ROOT/comms/$(date +%F)"
COMMS_FILE="$TODAY/backend-audit.md"
HANDOFF="$ROOT/.agents/provider-handoffs/backend-audit.md"
HOST_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
HOST_AUTH="$HOST_CODEX_HOME/auth.json"
HOST_PLUGIN_CATALOG="$HOST_CODEX_HOME/.tmp/plugins"
HOST_PLUGIN_CACHE="$HOST_CODEX_HOME/plugins/cache"
CODEX_BIN="$(command -v codex || true)"
CODEX_REAL="$(readlink -f "$CODEX_BIN" 2>/dev/null || true)"
MODE="${1:-}"

die() { echo "backend-audit sandbox: $*" >&2; exit 2; }

case "$MODE" in start|resume|self-test) ;; *) die "usage: $0 {start|resume|self-test}" ;; esac
command -v bwrap >/dev/null 2>&1 || die "Bubblewrap (bwrap) is required; refusing unsafe fallback"
command -v uv >/dev/null 2>&1 || die "uv is required to provision isolated audit tools"
[ -n "$CODEX_REAL" ] && [ -x "$CODEX_REAL" ] || die "Codex CLI not found"
[ -f "$HOST_AUTH" ] || die "Codex auth not found at configured CODEX_HOME/auth.json"
[ -d "$HOST_PLUGIN_CATALOG" ] || die "Codex plugin catalog unavailable; open /plugins once"

# Host-side preparation happens before confinement. Paths contain no machine-specific
# constants; every location derives from repository root, HOME, or CODEX_HOME.
mkdir -p \
  "$ROLE_DIR/notes" "$ROLE_DIR/drafts" "$CODEX_STATE/.tmp/plugins" \
  "$CODEX_STATE/plugins/cache" "$RUNTIME/tmp" "$REPORTS" \
  "$PROPOSALS" "$TODAY"
touch "$COMMS_FILE" "$HANDOFF" "$CODEX_STATE/auth.json" "$CODEX_STATE/config.toml"

# Plugin package is machine-local, never a committed $HOME path or project setting.
# Runtime state is isolated; catalog/package are exposed read-only inside sandbox.
if ! codex plugin list 2>/dev/null \
    | grep -q '^codex-security@openai-curated[[:space:]].*installed'; then
  codex plugin add codex-security@openai-curated >/dev/null \
    || die "could not provision codex-security plugin"
fi
[ -d "$HOST_PLUGIN_CACHE/openai-curated/codex-security" ] \
  || die "codex-security plugin cache unavailable after install"

if [ ! -x "$TOOLS_VENV/bin/python" ]; then
  uv venv --quiet --python 3.12 "$TOOLS_VENV" >/dev/null \
    || die "could not create isolated audit tool environment"
fi
uv pip install --quiet --python "$TOOLS_VENV/bin/python" --upgrade \
  --requirement "$ROLE_DIR/tooling-requirements.txt" >/dev/null \
  || die "could not provision pinned audit tools"
TOOLS_PYTHON_REAL="$(readlink -f "$TOOLS_VENV/bin/python")"
TOOLS_PYTHON_ROOT="$(dirname "$(dirname "$TOOLS_PYTHON_REAL")")"
TOOLS_PYTHON_LINK="$(readlink "$TOOLS_VENV/bin/python")"
TOOLS_PYTHON_MOUNT="$(dirname "$(dirname "$TOOLS_PYTHON_LINK")")"

CODEX_BIN_DIR="$(dirname "$CODEX_REAL")"

# Minimal filesystem view: system binaries/config, repository, isolated provider
# runtime. Normal home (SSH keys, gh credentials, cloud credentials) is absent.
# Codex's inner workspace sandbox blocks shell network; native web search remains
# available for primary-source security research.
BWRAP=(
  bwrap
  --unshare-all --share-net --die-with-parent
  --tmpfs /
  --proc /proc
  --dev /dev
  --ro-bind /usr /usr
  --symlink usr/bin /bin
  --symlink usr/lib /lib
  --symlink usr/lib64 /lib64
  --ro-bind /etc /etc
  --bind "$RUNTIME/tmp" /tmp
  --dir /home
  --dir "$HOME"
  --dir "$HOME/.local"
  --dir "$HOME/.local/share"
  --dir "$HOME/.local/share/uv"
  --dir "$HOME/.local/share/uv/python"
  --ro-bind "$TOOLS_PYTHON_ROOT" "$TOOLS_PYTHON_MOUNT"
  --dir "$(dirname "$(dirname "$(dirname "$ROOT")")")"
  --dir "$(dirname "$(dirname "$ROOT")")"
  --dir "$(dirname "$ROOT")"
  --ro-bind "$ROOT" "$ROOT"
  --bind "$CODEX_STATE" "$CODEX_STATE"
  --ro-bind "$HOST_AUTH" "$CODEX_STATE/auth.json"
  --ro-bind "$ROLE_DIR/codex.config.toml" "$CODEX_STATE/config.toml"
  --ro-bind "$HOST_PLUGIN_CATALOG" "$CODEX_STATE/.tmp/plugins"
  --ro-bind "$HOST_PLUGIN_CACHE" "$CODEX_STATE/plugins/cache"
  --bind "$ROLE_DIR/notes" "$ROLE_DIR/notes"
  --bind "$ROLE_DIR/drafts" "$ROLE_DIR/drafts"
  --bind "$REPORTS" "$REPORTS"
  --bind "$PROPOSALS" "$PROPOSALS"
  --bind "$COMMS_FILE" "$COMMS_FILE"
  --bind "$HANDOFF" "$HANDOFF"
  --dir /opt
  --ro-bind "$CODEX_BIN_DIR" /opt/clannon-codex
  --chdir "$ROLE_DIR"
  --setenv HOME "$HOME"
  --setenv CODEX_HOME "$CODEX_STATE"
  --setenv PATH "$TOOLS_VENV/bin:/opt/clannon-codex:/usr/local/bin:/usr/bin:/bin"
  --setenv GIT_CONFIG_GLOBAL /dev/null
  --setenv GIT_CONFIG_SYSTEM /dev/null
  --setenv GIT_TERMINAL_PROMPT 0
  --setenv TMPDIR /tmp
  --setenv PYTHONDONTWRITEBYTECODE 1
  --setenv SEMGREP_SEND_METRICS off
  --unsetenv SSH_AUTH_SOCK
  --unsetenv GH_TOKEN
  --unsetenv GITHUB_TOKEN
  --unsetenv AWS_ACCESS_KEY_ID
  --unsetenv AWS_SECRET_ACCESS_KEY
  --unsetenv AWS_SESSION_TOKEN
)

if [ "$MODE" = self-test ]; then
  positive="$ROLE_DIR/notes/.sandbox-write-test"
  report_positive="$REPORTS/.sandbox-write-test"
  proposal_positive="$PROPOSALS/.sandbox-write-test"
  source_negative="$ROOT/backend/.sandbox-write-test"
  git_negative="$ROOT/.git/.sandbox-write-test"
  charter_negative="$ROLE_DIR/CLAUDE.md"
  "${BWRAP[@]}" bash -c '
    set -eu
    touch "$1" "$2" "$3"
    ! touch "$4" 2>/dev/null
    ! touch "$5" 2>/dev/null
    ! { printf "tamper\n" >> "$6"; } 2>/dev/null
  ' bash "$positive" "$report_positive" "$proposal_positive" \
    "$source_negative" "$git_negative" "$charter_negative"
  unlink "$positive"
  unlink "$report_positive"
  unlink "$proposal_positive"
  [ ! -e "$source_negative" ] && [ ! -e "$git_negative" ] \
    || die "negative write test left unexpected files"
  "${BWRAP[@]}" /opt/clannon-codex/codex plugin list \
    | grep -q '^codex-security@openai-curated[[:space:]].*installed, enabled' \
    || die "codex-security plugin not visible inside isolated runtime"
  "${BWRAP[@]}" "$TOOLS_VENV/bin/python" -c \
    'import bandit, detect_secrets, pip_audit, semgrep' \
    || die "one or more pinned audit tools not visible inside sandbox"
  echo "backend-audit sandbox: PASS — outputs writable; source/.git/charter read-only; security tooling visible"
  exit 0
fi

CODEX=(
  /opt/clannon-codex/codex
  --no-alt-screen
  --sandbox workspace-write
  --ask-for-approval never
  --search
  --model gpt-5.6-sol
  --config 'model_reasoning_effort="xhigh"'
)
[ "$MODE" = resume ] && CODEX=(/opt/clannon-codex/codex resume --last "${CODEX[@]:1}")

exec "${BWRAP[@]}" "${CODEX[@]}"
