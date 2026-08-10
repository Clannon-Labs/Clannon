# Shared provider handoff — backend-audit

Independent source-read-only security research role. Read `backend-audit/CLAUDE.md`
after root boot files. Detailed unresolved findings stay in gitignored reports and
proposals; this tracked file contains safe continuity only.

## Current checkpoint — role runs on both providers, baseline audit not started (2026-08-10)

Role architecture and the Bubblewrap boundary exist and are proven for **Codex and
Claude Code**, through one launcher (`scripts/backend-audit-sandbox.sh
{start|resume|self-test} [--codex|--claude]`). Codex brings the Codex Security
plugin; Claude brings repo-local `backend-audit/.claude/` — the `audit-scanners`
skill plus the `attack-path-tracer` and `counterevidence` subagents. Pinned scanners
(bandit, detect-secrets, pip-audit, semgrep) are provisioned per machine into
`.agents/runtime/backend-audit/tools-venv/` for both.

Whichever provider you are: your profile is isolated (the owner's own Codex/Claude
state is not mounted), the source tree including this role's own `.claude/` rules is
read-only, and `self-test` is the only thing that proves it — run it after any change
to the launcher.

Scope is the Python backend plus root infrastructure; frontend and owner-only Rust
are excluded. First work is unchanged: pin revision, build the repository threat
model, run a standard baseline scan, then choose targeted deep scans from
attack-surface risk.

No security verdict exists yet. No finding is implied by role creation.

## Change note

Claude Code launch path added and proven (self-test PASS on both providers). Fixed a
defect that affected the Codex path too: `/etc/resolv.conf` is a symlink into `/run`,
which was not mounted, so name resolution failed inside the sandbox and any provider
would have retried its own API forever. The launcher now binds the resolv target and
`self-test` fails closed if resolution does not work.

## Previous checkpoint

Role created, baseline audit not started (2026-08-10). Role architecture and
Bubblewrap boundary existed; Codex Security plugin provisioned per machine by the
launcher. Same scope and same first work as above.
