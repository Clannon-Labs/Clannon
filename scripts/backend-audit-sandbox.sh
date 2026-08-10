#!/usr/bin/env bash
# Enforced launcher for the independent backend security auditor.
#
# Source tree is mounted read-only. Only auditor-owned evidence/continuity paths
# and isolated provider runtime state are writable. Prompt instructions are not the
# security boundary; Bubblewrap is. Missing Bubblewrap therefore fails closed.
#
# The provider (Codex or Claude Code) is a PARAMETER, not a second script: the
# mount policy is the security boundary, so it is written once and shared. A
# per-provider copy would be a second source of truth for the boundary and would
# drift silently — exactly what LAW 1 forbids.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROLE_DIR="$ROOT/backend-audit"
RUNTIME="${CLANNON_AUDIT_RUNTIME:-$ROOT/.agents/runtime/backend-audit}"
CODEX_STATE="$RUNTIME/codex-home"
CLAUDE_STATE="$RUNTIME/claude-home"
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
HOST_CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
HOST_CLAUDE_CREDS="$HOST_CLAUDE_HOME/.credentials.json"
CODEX_REAL="$(readlink -f "$(command -v codex || true)" 2>/dev/null || true)"
CLAUDE_REAL="$(readlink -f "$(command -v claude || true)" 2>/dev/null || true)"

MODE="${1:-}"
PROVIDER=codex
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --claude) PROVIDER=claude ;;
    --codex)  PROVIDER=codex ;;
    *)        MODE="" ;;
  esac
  shift
done

die() { echo "backend-audit sandbox: $*" >&2; exit 2; }

case "$MODE" in start|resume|self-test) ;; *) die "usage: $0 {start|resume|self-test} [--codex|--claude]" ;; esac
command -v bwrap >/dev/null 2>&1 || die "Bubblewrap (bwrap) is required; refusing unsafe fallback"
command -v uv >/dev/null 2>&1 || die "uv is required to provision isolated audit tools"

# Host-side preparation happens before confinement. Paths contain no machine-specific
# constants; every location derives from repository root, HOME, CODEX_HOME, or the
# Claude config dir.
mkdir -p \
  "$ROLE_DIR/notes" "$ROLE_DIR/drafts" "$RUNTIME/tmp" \
  "$REPORTS" "$PROPOSALS" "$TODAY"
touch "$COMMS_FILE" "$HANDOFF"

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

prepare_codex() {
  [ -n "$CODEX_REAL" ] && [ -x "$CODEX_REAL" ] || die "Codex CLI not found"
  [ -f "$HOST_AUTH" ] || die "Codex auth not found at configured CODEX_HOME/auth.json"
  [ -d "$HOST_PLUGIN_CATALOG" ] || die "Codex plugin catalog unavailable; open /plugins once"

  mkdir -p "$CODEX_STATE/.tmp/plugins" "$CODEX_STATE/plugins/cache"
  touch "$CODEX_STATE/auth.json" "$CODEX_STATE/config.toml"

  # Plugin package is machine-local, never a committed $HOME path or project setting.
  # Runtime state is isolated; catalog/package are exposed read-only inside sandbox.
  if ! codex plugin list 2>/dev/null \
      | grep -q '^codex-security@openai-curated[[:space:]].*installed'; then
    codex plugin add codex-security@openai-curated >/dev/null \
      || die "could not provision codex-security plugin"
  fi
  [ -d "$HOST_PLUGIN_CACHE/openai-curated/codex-security" ] \
    || die "codex-security plugin cache unavailable after install"
}

prepare_claude() {
  [ -n "$CLAUDE_REAL" ] && [ -x "$CLAUDE_REAL" ] || die "Claude Code CLI not found"
  [ -f "$HOST_CLAUDE_CREDS" ] || die "Claude credentials not found; run 'claude auth' on the host first"
  command -v python3 >/dev/null 2>&1 || die "python3 is required to seed isolated Claude state"

  mkdir -p "$CLAUDE_STATE"
  touch "$CLAUDE_STATE/.credentials.json"

  # `.claude.json` is Claude's own mutable state, not config, so it is SEEDED and
  # merged rather than mounted: a fresh isolated profile otherwise blocks the very
  # first interactive turn on three dialogs nobody is there to answer. Each flag
  # below was derived by accepting the real dialog once and diffing the file, not
  # guessed. The external-imports approval is keyed on the repository root (root
  # CLAUDE.md imports AGENTS.md), the trust flags on the role directory.
  python3 - "$CLAUDE_STATE/.claude.json" "$ROOT" "$ROLE_DIR" <<'PY'
import json, pathlib, sys

path, root, role_dir = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
try:
    state = json.loads(path.read_text())
except (FileNotFoundError, ValueError):
    state = {}
state["hasCompletedOnboarding"] = True
projects = state.setdefault("projects", {})
projects.setdefault(role_dir, {}).update({
    "hasTrustDialogAccepted": True,
    "hasCompletedProjectOnboarding": True,
    "hasClaudeMdExternalIncludesApproved": True,
    "hasClaudeMdExternalIncludesWarningShown": True,
})
projects.setdefault(root, {}).update({
    "hasTrustDialogAccepted": True,
    "hasClaudeMdExternalIncludesApproved": True,
    "hasClaudeMdExternalIncludesWarningShown": True,
})
path.write_text(json.dumps(state, indent=2))
PY

  # Machine-local user-scope settings for the isolated profile. The auditor's actual
  # policy is the TRACKED backend-audit/.claude/settings.json, which is mounted
  # read-only with the rest of the source — the auditor cannot edit its own rules.
  cat > "$CLAUDE_STATE/settings.json" <<'JSON'
{
  "skipDangerousModePermissionPrompt": true,
  "includeCoAuthoredBy": false
}
JSON
}

case "$PROVIDER" in
  codex)  prepare_codex ;;
  claude) prepare_claude ;;
esac

# Minimal filesystem view: system binaries/config, repository, isolated provider
# runtime. Normal home (SSH keys, gh credentials, cloud credentials) is absent.
# /etc/resolv.conf is a symlink into /run on systemd-resolved hosts, so the target
# is bound explicitly — without it name resolution fails inside the sandbox and the
# provider cannot reach its own API (measured, 2026-08-10).
RESOLV_REAL="$(readlink -f /etc/resolv.conf 2>/dev/null || true)"
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
  --bind "$ROLE_DIR/notes" "$ROLE_DIR/notes"
  --bind "$ROLE_DIR/drafts" "$ROLE_DIR/drafts"
  --bind "$REPORTS" "$REPORTS"
  --bind "$PROPOSALS" "$PROPOSALS"
  --bind "$COMMS_FILE" "$COMMS_FILE"
  --bind "$HANDOFF" "$HANDOFF"
  --dir /opt
  --chdir "$ROLE_DIR"
  --setenv HOME "$HOME"
  --setenv PATH "$TOOLS_VENV/bin:/opt/clannon-provider:/usr/local/bin:/usr/bin:/bin"
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
[ -n "$RESOLV_REAL" ] && case "$RESOLV_REAL" in
  /etc/*) ;;
  *) BWRAP+=( --ro-bind "$RESOLV_REAL" "$RESOLV_REAL" ) ;;
esac

# Provider-specific mounts. Only the runtime state, credential, and binary differ;
# everything above — the actual boundary — is shared.
case "$PROVIDER" in
  codex)
    BWRAP+=(
      --bind "$CODEX_STATE" "$CODEX_STATE"
      --ro-bind "$HOST_AUTH" "$CODEX_STATE/auth.json"
      --ro-bind "$ROLE_DIR/codex.config.toml" "$CODEX_STATE/config.toml"
      --ro-bind "$HOST_PLUGIN_CATALOG" "$CODEX_STATE/.tmp/plugins"
      --ro-bind "$HOST_PLUGIN_CACHE" "$CODEX_STATE/plugins/cache"
      --ro-bind "$(dirname "$CODEX_REAL")" /opt/clannon-provider
      --setenv CODEX_HOME "$CODEX_STATE"
    )
    PROVIDER_BIN=/opt/clannon-provider/codex
    ;;
  claude)
    BWRAP+=(
      --bind "$CLAUDE_STATE" "$CLAUDE_STATE"
      --ro-bind "$HOST_CLAUDE_CREDS" "$CLAUDE_STATE/.credentials.json"
      --ro-bind "$CLAUDE_REAL" /opt/clannon-provider/claude
      --setenv CLAUDE_CONFIG_DIR "$CLAUDE_STATE"
    )
    PROVIDER_BIN=/opt/clannon-provider/claude
    ;;
esac

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

  # A provider that cannot resolve its own API silently retries forever, so name
  # resolution is a launch prerequisite and is proven, not assumed.
  "${BWRAP[@]}" getent hosts api.anthropic.com >/dev/null \
    || die "name resolution failed inside sandbox (offline host, or /etc/resolv.conf target not mounted)"
  "${BWRAP[@]}" "$TOOLS_VENV/bin/python" -c \
    'import bandit, detect_secrets, pip_audit, semgrep' \
    || die "one or more pinned audit tools not visible inside sandbox"

  case "$PROVIDER" in
    codex)
      "${BWRAP[@]}" "$PROVIDER_BIN" plugin list \
        | grep -q '^codex-security@openai-curated[[:space:]].*installed, enabled' \
        || die "codex-security plugin not visible inside isolated runtime"
      ;;
    claude)
      "${BWRAP[@]}" "$PROVIDER_BIN" --version >/dev/null \
        || die "Claude Code did not start inside isolated runtime"
      # Isolation proof: the auditor's profile is the runtime one, and the owner's
      # own Claude state (accounts, MCP servers, project history) is not present.
      "${BWRAP[@]}" bash -c '
        set -eu
        [ -r "$1/.credentials.json" ]
        ! [ -w "$1/.credentials.json" ]
        ! [ -e "$2/.claude.json" ]
        ! [ -e "$3" ]
      ' bash "$CLAUDE_STATE" "$HOME" "$HOST_CLAUDE_HOME/settings.json" \
        || die "Claude runtime isolation check failed"
      ;;
  esac
  echo "backend-audit sandbox: PASS ($PROVIDER) — outputs writable; source/.git/charter read-only; DNS, security tooling, and provider runtime verified"
  exit 0
fi

case "$PROVIDER" in
  codex)
    LAUNCH=(
      "$PROVIDER_BIN"
      --no-alt-screen
      --sandbox workspace-write
      --ask-for-approval never
      --search
      --model gpt-5.6-sol
      --config 'model_reasoning_effort="xhigh"'
    )
    [ "$MODE" = resume ] && LAUNCH=("$PROVIDER_BIN" resume --last "${LAUNCH[@]:1}")
    ;;
  claude)
    # Bypass mode matches the other roles' unattended posture. It is safe HERE for a
    # reason the other roles cannot claim: the tree is mounted read-only, so the
    # permission layer is defence in depth rather than the boundary. `--add-dir`
    # carries the repository root because the auditor's cwd is its own role
    # directory while its subject is `backend/` and root config.
    LAUNCH=(
      "$PROVIDER_BIN"
      --dangerously-skip-permissions
      --add-dir "$ROOT"
      --model claude-opus-5
      --effort xhigh
    )
    [ "$MODE" = resume ] && LAUNCH+=(--continue)
    ;;
esac

exec "${BWRAP[@]}" "${LAUNCH[@]}"
