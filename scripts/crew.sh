#!/usr/bin/env bash
#
# crew.sh — start, watch, and stop the Clannon agents.
#
#   ./scripts/crew.sh start <role> [--codex|--claude] [--fresh]
#   ./scripts/crew.sh status
#   ./scripts/crew.sh attach <role>
#   ./scripts/crew.sh stop <role>
#   ./scripts/crew.sh run <role> --brief <file> [--claude|--codex]
#
# Roles: backend frontend memory orchestration security api backend-audit release
#
# TWO WAYS AN AGENT RUNS — they do not overlap:
#   start/attach  interactive session in tmux. For the OWNER to drive an agent.
#   run           headless one-shot worker. For the COORDINATOR to delegate a
#                 scoped task. No tmux, no session, exits when done.
# Neither injects into a live session, so the pull-not-push rule holds for both
# (docs/architecture/CREW_WORKFLOW.md §2.1, §4.4).
#
# THE ONE RULE THIS SCRIPT EXISTS TO RESPECT:
#   Nothing here ever types into a RUNNING agent's session. There is no
#   send-keys anywhere in this file. `start` launches an agent as the tmux
#   session's own initial command; if a role is already up, start refuses and
#   does nothing. Messaging between agents is pull-based via comms/ — see
#   docs/architecture/CREW_WORKFLOW.md §2.1.
#
# Replaces (all deleted): clannon-standup.sh, clannon-provider-supervisor.sh,
# clannon-provider-status.sh, agent-session.sh, proposal-wake.sh,
# clannon-heartbeat.sh, and the systemd wake/heartbeat units. See
# docs/architecture/CREW_WORKFLOW.md §8 for why each one went.

set -uo pipefail   # no -e: a failure on one role must not abort a multi-role loop

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUDIT_RUNTIME="${CLANNON_AUDIT_RUNTIME:-$ROOT/.agents/runtime/backend-audit}"
ROLES="backend frontend memory orchestration security api backend-audit release"

die() { echo "crew: $*" >&2; exit 2; }

# --- commit identity -------------------------------------------------------
# Every agent this script launches commits as clannon-bot, whichever provider it
# runs on. This MUST live here rather than in a provider's own settings: Claude
# Code reads ~/.claude/settings.json, Codex reads nothing of the sort, and the
# repo's old local `user.name` "solved" that by forcing the bot identity onto the
# owner's own commits too. Exporting at the launcher is the only place that is
# both provider-agnostic and cannot touch a human's terminal.
# `.githooks/pre-commit` independently refuses a commit that gets this wrong.
BOT_NAME="clannon-bot"
BOT_EMAIL="293251899+clannon-bot@users.noreply.github.com"

agent_env() {   # role -> the `env` prefix that stamps an agent's commits
  printf 'env CLANNON_AGENT=%q GIT_AUTHOR_NAME=%q GIT_AUTHOR_EMAIL=%q GIT_COMMITTER_NAME=%q GIT_COMMITTER_EMAIL=%q ' \
    "$1" "$BOT_NAME" "$BOT_EMAIL" "$BOT_NAME" "$BOT_EMAIL"
}

"$(cd "$(dirname "$0")" && pwd)/setup-hooks.sh" 2>/dev/null || true

dir_for() {
  case "$1" in
    backend)       echo "$ROOT" ;;
    frontend)      echo "$ROOT/frontend" ;;
    memory)        echo "$ROOT/backend/core/memory" ;;
    orchestration) echo "$ROOT/backend/core/orchestrator" ;;
    security)      echo "$ROOT/backend/security" ;;
    api)           echo "$ROOT/backend/api" ;;
    backend-audit) echo "$ROOT/backend-audit" ;;
    release)       echo "$ROOT/release" ;;
    *)             return 1 ;;
  esac
}

valid_role() { dir_for "$1" >/dev/null 2>&1; }

# Specialists run on Sonnet to keep token burn down; the coordinator and the
# frontend keep the stronger default model. The quality net is the coordinator's
# review of every specialist change — not the model tier.
is_specialist() {
  case "$1" in memory|orchestration|security|api) return 0 ;; *) return 1 ;; esac
  # NOTE: `release` is deliberately absent — it is a conversational role the
  # owner drives directly, so it keeps the stronger default model.
}

is_auditor() { [ "$1" = backend-audit ]; }

# --- session liveness -------------------------------------------------------
# A tmux session can outlive its agent: when claude/codex exits, the wrapper
# shell stays and the session looks "up" while nothing is working. Two of the
# six emergency fixes on the old scripts were about exactly this. Distinguish
# properly: a session is LIVE only if the pane is running a provider, or a
# shell that has a provider as a child.

session_exists() { tmux has-session -t "clannon-$1" 2>/dev/null; }

live_provider() {   # echoes "claude" | "codex" | "" (empty = no agent running)
  local session="clannon-$1" cmd pane_pid child args
  cmd="$(tmux display-message -p -t "$session" '#{pane_current_command}' 2>/dev/null || true)"
  case "$cmd" in
    claude|codex) echo "$cmd"; return 0 ;;
  esac
  pane_pid="$(tmux display-message -p -t "$session" '#{pane_pid}' 2>/dev/null || true)"
  [ -n "$pane_pid" ] || { echo ""; return 0; }
  for child in $(pgrep -P "$pane_pid" 2>/dev/null); do
    args="$(ps -o args= -p "$child" 2>/dev/null)"
    case "$args" in
      claude\ *|*/claude\ *) echo "claude"; return 0 ;;
      codex\ *|*/codex\ *)   echo "codex";  return 0 ;;
    esac
  done
  echo ""
}

is_live() { [ -n "$(live_provider "$1")" ]; }

# --- launch -----------------------------------------------------------------

# Does Claude have a resumable conversation for this directory? Claude stores
# transcripts per working directory under ~/.claude/projects/<path-with-dashes>.
# We check BEFORE launching rather than passing --continue and hoping: a
# --continue with no prior session exits immediately with "No conversation found
# to continue", which would drop the pane straight to a dead shell. Detecting up
# front means there is no failure path to recover from.
claude_has_session() {
  local dir="$1" encoded projects_dir
  encoded="${dir//\//-}"
  # The auditor runs against an isolated config dir so it never sees the owner's
  # own Claude state; its transcripts land there too, not under $HOME.
  if [ "$dir" = "$ROOT/backend-audit" ]; then
    projects_dir="$AUDIT_RUNTIME/claude-home/projects"
  else
    projects_dir="$HOME/.claude/projects"
  fi
  compgen -G "$projects_dir/$encoded/*.jsonl" >/dev/null 2>&1
}

# Codex stores the cwd and launch source in the first `session_meta` record.
# Match both: cwd keeps roles isolated, while source=cli excludes headless
# `codex exec` workers that happen to run inside the same module.
codex_has_session() {
  local dir="$1" sessions_dir file metadata
  if [ "$dir" = "$ROOT/backend-audit" ]; then
    sessions_dir="$AUDIT_RUNTIME/codex-home/sessions"
  else
    sessions_dir="${CODEX_HOME:-$HOME/.codex}/sessions"
  fi
  [ -d "$sessions_dir" ] || return 1

  while IFS= read -r -d '' file; do
    IFS= read -r metadata < "$file" || continue
    if [[ $metadata == *'"type":"session_meta"'* \
      && $metadata == *'"cwd":"'"$dir"'"'* \
      && $metadata == *'"source":"cli"'* ]]; then
      return 0
    fi
  done < <(find "$sessions_dir" -type f -name '*.jsonl' -print0 2>/dev/null)
  return 1
}

provider_has_session() {
  case "$1" in
    claude) claude_has_session "$2" ;;
    codex)  codex_has_session "$2" ;;
    *)      return 1 ;;
  esac
}

launch_command() {   # role provider fresh dir -> the shell command the session runs
  local role="$1" provider="$2" fresh="$3" dir="$4" cmd
  if is_auditor "$role"; then
    # Both providers go through the same enforced launcher: the Bubblewrap mount
    # policy IS the boundary, so it is written once and takes the provider as a
    # parameter. Prove it after touching it — `backend-audit-sandbox.sh self-test
    # --claude|--codex`.
    if [ "$fresh" = no ] && provider_has_session "$provider" "$dir"; then
      cmd="$(printf '%q' "$ROOT/scripts/backend-audit-sandbox.sh") resume --$provider"
    else
      cmd="$(printf '%q' "$ROOT/scripts/backend-audit-sandbox.sh") start --$provider"
    fi
    cmd="$(agent_env "$role")$cmd"
    echo "$cmd; echo; echo '[crew] auditor exited — session kept for inspection. Ctrl-b d to detach.'; exec bash"
    return
  fi
  case "$provider" in
    claude)
      cmd="claude --dangerously-skip-permissions"
      is_specialist "$role" && cmd="$cmd --model claude-sonnet-5"
      if [ "$fresh" = no ] && claude_has_session "$dir"; then
        cmd="$cmd --continue"
      fi
      ;;
    codex)
      # danger-full-access deliberately: workspace-write denied .git/index.lock
      # and .agents/ writes, which blocked a specialist from committing its own
      # work and updating its own handoff. Same unattended posture as Claude's
      # --dangerously-skip-permissions.
      # Inline mode matches Claude's terminal behavior: tmux owns scrollback,
      # while Codex keeps Up/Down and Ctrl-R available for prompt history.
      cmd="codex"
      if [ "$fresh" = no ] && codex_has_session "$dir"; then
        # Current Codex scopes --last to cwd unless --all is passed. Running the
        # command from the role directory therefore resumes only that role.
        cmd="$cmd resume --last"
      fi
      cmd="$cmd --no-alt-screen --sandbox danger-full-access --ask-for-approval never"
      ;;
  esac
  # Prefix with the agent identity so the commits this session makes are the
  # bot's, on either provider. The trailing `exec bash` is deliberately NOT
  # wrapped: once the agent exits, the leftover shell is a human's again.
  cmd="$(agent_env "$role")$cmd"
  # Keep the session alive after the agent exits so its scrollback stays
  # inspectable; `crew.sh start` will recycle the dead shell on the next run.
  echo "$cmd; echo; echo '[crew] agent exited — session kept for inspection. Ctrl-b d to detach.'; exec bash"
}

cmd_start() {
  local role="" provider="" fresh=no arg
  for arg in "$@"; do
    case "$arg" in
      --codex)  provider=codex ;;
      --claude) provider=claude ;;
      --fresh)  fresh=yes ;;
      --*)      die "unknown flag: $arg" ;;
      *)        role="$arg" ;;
    esac
  done
  [ -n "$role" ] || die "usage: crew.sh start <role> [--codex|--claude] [--fresh]"
  valid_role "$role" || die "unknown role: $role (roles: $ROLES)"
  if [ -z "$provider" ]; then
    if is_auditor "$role"; then provider=codex; else provider=claude; fi
  fi

  local session="clannon-$role" dir running
  dir="$(dir_for "$role")"

  if session_exists "$role"; then
    running="$(live_provider "$role")"
    if [ -n "$running" ]; then
      echo "crew: $session is already running ($running) — nothing changed."
      echo "crew: watch it with:  ./scripts/crew.sh attach $role"
      return 0
    fi
    echo "crew: $session exists but no agent is running in it — recycling."
    tmux kill-session -t "$session" 2>/dev/null
  fi

  local mode
  if [ "$fresh" = yes ]; then mode="fresh (forced)"
  elif provider_has_session "$provider" "$dir"; then mode="resuming prior conversation"
  else mode="fresh (no prior conversation for this directory)"
  fi

  tmux new-session -d -s "$session" -c "$dir" "$(launch_command "$role" "$provider" "$fresh" "$dir")"
  echo "crew: started $session  [$provider, $mode]  cwd $dir"
  echo "crew: watch it with:  ./scripts/crew.sh attach $role"
}

cmd_status() {
  local role state provider dir_note
  printf 'Clannon crew — %s\n\n' "$(date '+%F %T %Z')"
  printf '  %-14s %-10s %s\n' ROLE STATE PROVIDER
  for role in $ROLES; do
    if ! session_exists "$role"; then
      state="stopped"; provider="-"
    else
      provider="$(live_provider "$role")"
      if [ -n "$provider" ]; then state="running"; else state="dead-shell"; provider="-"; fi
    fi
    printf '  %-14s %-10s %s\n' "$role" "$state" "$provider"
  done
  echo
  echo "  stopped     no tmux session — start with: crew.sh start <role>"
  echo "  dead-shell  session outlived its agent — crew.sh start <role> recycles it"
  echo
  local today="$ROOT/comms/$(date +%F)"
  if [ -d "$today" ]; then
    echo "  today's comms ($(date +%F)):"
    for f in "$today"/*.md; do
      [ -e "$f" ] || continue
      printf '    %-16s %s lines\n' "$(basename "$f" .md)" "$(wc -l < "$f" | tr -d ' ')"
    done
  else
    echo "  today's comms: none yet ($today)"
  fi
}

cmd_attach() {
  local role="${1:-}"
  [ -n "$role" ] || die "usage: crew.sh attach <role>"
  valid_role "$role" || die "unknown role: $role (roles: $ROLES)"
  session_exists "$role" || die "clannon-$role is not running — start it with: crew.sh start $role"
  echo "crew: attaching to clannon-$role — detach with Ctrl-b then d (do NOT type 'exit')."
  exec tmux attach -t "clannon-$role"
}

cmd_stop() {
  local role="${1:-}"
  [ -n "$role" ] || die "usage: crew.sh stop <role>"
  valid_role "$role" || die "unknown role: $role (roles: $ROLES)"
  session_exists "$role" || { echo "crew: clannon-$role is not running."; return 0; }
  if is_live "$role"; then
    echo "crew: WARNING — an agent is running in clannon-$role."
    echo "crew: it will not get a chance to write its handoff (.agents/provider-handoffs/$role.md)."
    echo "crew: prefer attaching and letting it stop cleanly. Killing in 5s — Ctrl-C to abort."
    sleep 5
  fi
  tmux kill-session -t "clannon-$role" 2>/dev/null
  echo "crew: stopped clannon-$role."
}

# --- run: headless delegated worker ----------------------------------------
# The coordinator writes a brief, dispatches a worker into one role's tree, and
# reads the result back from a file. The worker never commits (see the mandate
# appended to every brief below): two workers racing on .git/index.lock is a
# real failure we have already seen once, and reviewing before committing is
# the coordinator's job anyway.

RUNS_DIR="$ROOT/.agents/runs"

resolve_provider() {   # explicit flag wins; else the policy file; else codex
  local explicit="$1" policy=""
  if [ -n "$explicit" ]; then echo "$explicit"; return; fi
  [ -f "$ROOT/.agents/provider-policy" ] &&
    policy="$(sed -n 's/^PROVIDER_DEFAULT=//p' "$ROOT/.agents/provider-policy" | tail -n1)"
  echo "${policy:-codex}"
}

cmd_run() {
  local role="" brief="" provider="" arg next=""
  local -a subdirs=()
  for arg in "$@"; do
    case "$next" in
      brief) brief="$arg"; next=""; continue ;;
      dir)   subdirs+=("$arg"); next=""; continue ;;
    esac
    case "$arg" in
      --brief)  next=brief ;;
      --dir)    next=dir ;;
      --claude) provider=claude ;;
      --codex)  provider=codex ;;
      --*)      die "unknown flag: $arg" ;;
      *)        role="$arg" ;;
    esac
  done
  [ -n "$role" ] && [ -n "$brief" ] || die "usage: crew.sh run <role> --brief <file> [--claude|--codex]"
  valid_role "$role" || die "unknown role: $role (roles: $ROLES)"
  if is_auditor "$role"; then
    die "backend-audit is a persistent, read-only research role; use: crew.sh start backend-audit"
  fi
  # The coordinator owns real trees too (foundation/, core/llm, core/pipeline.py,
  # config/, scripts/, docs/). Dispatching a worker into one of those is exactly how
  # it delegates instead of doing the labour itself — but it must be SCOPED, because
  # the backend "tree" is the whole repo and an unscoped worker there would have no
  # ownership boundary at all. Hence --dir is mandatory for the backend role.
  if [ "$role" = backend ] && [ "${#subdirs[@]}" -eq 0 ]; then
    die "dispatching to 'backend' needs --dir <path> to scope it (its tree is the whole repo). e.g. --dir backend/core/llm"
  fi
  [ -f "$brief" ] || die "brief not found: $brief"
  provider="$(resolve_provider "$provider")"
  case "$provider" in claude|codex) ;; *) die "bad provider: $provider" ;; esac

  local dir lock stamp out log
  dir="$(dir_for "$role")"
  # --dir is REPEATABLE, because real ownership is almost always a SET of paths:
  # the source plus the tests that prove it. The specialist charters already work
  # this way (api owns backend/api/** *and* a list of test files). A single-path
  # scope made every honest task fail — a worker told "you own core/llm" cannot
  # write the test that proves its change, and correctly refuses.
  local -a owned=()
  if [ "${#subdirs[@]}" -gt 0 ]; then
    local d
    for d in "${subdirs[@]}"; do
      case "$d" in /*) ;; *) d="$ROOT/$d" ;; esac
      # A path may name a file the worker is supposed to CREATE — granting the test
      # that proves a change is the common case, and the test does not exist yet.
      # Requiring existence made that ungrantable: the dispatch mandate tells the
      # worker to stop when the brief needs an unlisted path, so the task could not
      # be scoped at all. An existing parent directory is the honest floor — it still
      # catches the typo this check exists for, without refusing new files.
      [ -e "$d" ] || [ -d "$(dirname "$d")" ] \
        || die "--dir does not exist, and neither does its parent: $d"
      # backend-rust/ is the OWNER's tree — they are hand-writing the Rust rewrite
      # there and asked, in that directory's own README, that nothing else touch it.
      # Enforced here rather than left as a note: a note is what an agent reads AFTER
      # editing. The existing-parent relaxation directly above widened what --dir
      # accepts, which makes this guard worth more, not less.
      case "$d" in
        "$ROOT"/backend-rust|"$ROOT"/backend-rust/*)
          die "backend-rust/ is the owner's tree — never dispatch a worker into it" ;;
      esac
      owned+=("$d")
    done
    # cwd must be a directory that exists — the first path may be a yet-to-be-created
    # file, in which case its parent is the right place to stand.
    dir="${owned[0]}"
    [ -d "$dir" ] || dir="$(dirname "$dir")"
  else
    owned=("$dir")
  fi
  mkdir -p "$RUNS_DIR"
  lock="$RUNS_DIR/$role.lock"

  # One worker per role at a time. Roles own disjoint trees, so this is all the
  # mutual exclusion needed to keep two workers off the same files.
  if [ -e "$lock" ] && kill -0 "$(cat "$lock" 2>/dev/null)" 2>/dev/null; then
    die "a worker is already running for '$role' (pid $(cat "$lock")). Wait for it, or clear $lock if stale."
  fi

  # Refuse to dispatch into a tree the coordinator has left dirty — the worker
  # would build on top of uncommitted work and the diff would be unreviewable.
  if [ -n "$(git -C "$ROOT" status --porcelain -- "${owned[@]}" 2>/dev/null)" ]; then
    echo "crew: WARNING — '$role' tree has uncommitted changes:" >&2
    git -C "$ROOT" status --short -- "${owned[@]}" >&2
    echo "crew: commit or stash them first so the worker's diff is reviewable." >&2
    exit 3
  fi

  stamp="$(date +%Y%m%d-%H%M%S)"
  out="$RUNS_DIR/$stamp-$role.out"
  log="$RUNS_DIR/$stamp-$role.log"

  # Every brief gets the same non-negotiable footer. Structural, not per-brief:
  # a mandate the coordinator has to remember to type is one it will forget.
  local full_brief worker_identity proposal_inbox
  if [ "$role" = backend ]; then
    worker_identity="backend-worker"
    proposal_inbox="$ROOT/proposals/to-backend/from_workers"
  else
    worker_identity="$role-worker"
    proposal_inbox="$ROOT/proposals/to-backend"
  fi
  mkdir -p "$proposal_inbox"
  full_brief="$(cat "$brief")
$(cat <<EOF

---
DISPATCH MANDATE (added automatically by crew.sh — applies to this whole task):
- Your worker identity is '$worker_identity'. The persistent reviewer/integrator
  is 'backend-coordinator'; you are not a second persistent backend agent.
- You are working in the '$role' role. For this task you own EXACTLY these paths,
  and nothing else:
$(printf "    %s\n" "${owned[@]}")
  Your working directory is $dir. Read the nearest CLAUDE.md at or above it for
  the rules that apply. If the brief needs a path that is NOT in the list above,
  stop and say which one — that is the dispatcher's mistake, not yours.
- Do NOT commit and do NOT push. Leave your changes uncommitted in the working
  tree. The backend coordinator reviews and commits everything. This is not
  negotiable: concurrent workers racing on .git/index.lock is a real failure
  mode we have hit before.
- Do NOT edit any tree other than your own. If the task seems to need one,
  stop and say so in your final message instead of doing it.
- If you discover a decision that requires the backend coordinator's ruling,
  write a proposal under:
    $proposal_inbox
  Use 'From: $worker_identity' and 'To: backend-coordinator'. This proposal
  route is the only exception to the owned-path edit list above. Do not put
  coordinator-to-worker task briefs in a proposal inbox.
- Verify your work (run the relevant tests) and say exactly what you ran and
  what the result was. Never claim a pass you did not observe.
- Your FINAL MESSAGE is the only thing the coordinator reads directly. Make it
  self-contained: what you changed (with file paths), what you verified and
  how, and anything you found but deliberately did not do.
EOF
)"

  echo "crew: dispatching $role worker  [$provider]  cwd $dir"
  echo "crew: brief   $brief"
  echo "crew: output  $out"

  local rc=0 started ended
  started="$(date +%s)"
  echo $$ > "$lock"
  # Release the lock even on SIGTERM/SIGINT — a killed dispatcher used to leave a
  # stale lock behind (the liveness check self-heals, but the file lingered).
  # DOUBLE quotes: $lock must expand NOW, while it is in scope. Single quotes
  # defer expansion to trap-firing time, and the EXIT trap fires after this
  # function has returned — so `local lock` is already gone and `set -u` aborts
  # with "lock: unbound variable" after every otherwise-successful dispatch.
  # The trap then never runs, which is the opposite of what it exists to do.
  trap "rm -f '$lock'" EXIT INT TERM
  # Headless workers are not supposed to commit at all — the coordinator reviews
  # and commits their diff. Stamped anyway: "shouldn't" is not an enforcement,
  # and a worker that does commit must not do it under the owner's name.
  export CLANNON_AGENT="$role-worker"
  export GIT_AUTHOR_NAME="$BOT_NAME" GIT_AUTHOR_EMAIL="$BOT_EMAIL"
  export GIT_COMMITTER_NAME="$BOT_NAME" GIT_COMMITTER_EMAIL="$BOT_EMAIL"
  case "$provider" in
    claude)
      # </dev/null is REQUIRED, not tidiness: both CLIs read stdin in addition to
      # the prompt argument. With an inherited pipe that never reaches EOF (exactly
      # what happens when this script is backgrounded — the normal mode for a long
      # task) the provider blocks forever having done nothing. A short foreground
      # test hides it, because there stdin EOFs immediately.
      # Sonnet for delegated implementation, same reasoning as the interactive
      # specialist default (see is_specialist): a headless worker runs ONE scoped
      # brief and its diff is reviewed before it lands, so the quality net is the
      # coordinator's review, not the model tier. Opus budget stays with
      # coordination and review, which is where it actually pays.
      ( cd "$dir" && claude -p "$full_brief" --model claude-sonnet-5 --dangerously-skip-permissions ) \
        </dev/null >"$out" 2>"$log" || rc=$?
      ;;
    codex)
      codex exec "$full_brief" -C "$dir" --skip-git-repo-check \
        --sandbox danger-full-access -o "$out" </dev/null >"$log" 2>&1 || rc=$?
      ;;
  esac
  ended="$(date +%s)"
  rm -f "$lock"

  # Provenance: the dispatcher records who did what, because a worker can
  # forget to and the dispatcher cannot. One tracked line in comms/, full logs
  # in gitignored .agents/runs/.
  local today="$ROOT/comms/$(date +%F)" line
  mkdir -p "$today"
  line="- \`$(date +%H:%M)\` **$role** worker via **$provider** — $(basename "$brief") — exit $rc, $((ended-started))s — output: \`.agents/runs/$(basename "$out")\`"
  if ! grep -q "^## dispatched workers" "$today/backend.md" 2>/dev/null; then
    printf '\n## dispatched workers\n' >> "$today/backend.md"
  fi
  echo "$line" >> "$today/backend.md"

  echo "crew: worker finished — exit $rc, $((ended-started))s"
  echo "crew: --- final message ---"
  cat "$out" 2>/dev/null
  return $rc
}

case "${1:-}" in
  start)  shift; cmd_start "$@" ;;
  run)    shift; cmd_run "$@" ;;
  status) cmd_status ;;
  attach) shift; cmd_attach "$@" ;;
  stop)   shift; cmd_stop "$@" ;;
  -h|--help|"")
    sed -n '3,26p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *) die "unknown command: $1 (try: start | status | attach | stop)" ;;
esac
