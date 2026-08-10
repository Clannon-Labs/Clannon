# Backend Audit role

Independent source-read-only security research role.

- Charter: `CLAUDE.md` (`AGENTS.md` points Codex to same source)
- Safe durable template: `../.agents/templates/AUDIT_FINDING.md` (shared with `frontend-audit`)
- Local research: `notes/`, `drafts/`
- Deep audits: `../reports/backend-audit/report_vN.md`
- Actionable findings: `../proposals/to-backend/from-backend-audit/`
- Cross-provider continuity: `../.agents/provider-handoffs/backend-audit.md`

Launch:

```bash
./scripts/crew.sh start backend-audit           # Claude Code (default)
./scripts/crew.sh start backend-audit --codex   # Codex
./scripts/crew.sh run backend-audit --codex \
  --brief proposals/to-backend-audit/<assignment>.md  # unattended bounded audit
```

Both providers go through one enforced launcher, so the boundary cannot differ
between interactive and unattended use either. It requires Bubblewrap, provisions the provider's isolated runtime
(Codex Security plugin state, or a Claude config dir the owner's own profile never
touches) plus pinned Bandit, detect-secrets, pip-audit, and Semgrep. Tooling lives
under gitignored `.agents/runtime/backend-audit/`, never the project venv. The
launcher fails closed if source-read-only enforcement is unavailable. Ignored local
`.env*` files are masked with `/dev/null` inside the sandbox (examples/templates stay
readable), so read-only source access never implies access to deployment secrets.

Claude-specific equipment is repo-local and tracked, not installed from a
marketplace: `.claude/settings.json` (denied write/publish commands),
`.claude/skills/audit-scanners/`, and the shared root `.claude/agents/`
(`attack-path-tracer`, `counterevidence`).

Run the boundary proof for the provider you touched — it covers writable outputs,
read-only source/`.git`/charter, ignored-env masking, name resolution, scanner
visibility, and provider startup:

```bash
./scripts/audit-sandbox.sh backend-audit self-test --codex
./scripts/audit-sandbox.sh backend-audit self-test --claude
```

Detailed notes, drafts, reports, and proposals are gitignored because unresolved
vulnerability details should not be published with source. Handoff and comms carry
only safe summaries.
