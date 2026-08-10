# Backend Audit role

Independent source-read-only security research role.

- Charter: `CLAUDE.md` (`AGENTS.md` points Codex to same source)
- Safe durable template: `templates/FINDING.md`
- Local research: `notes/`, `drafts/`
- Deep audits: `../reports/backend-audit/report_vN.md`
- Actionable findings: `../proposals/to-backend/from-backend-audit/`
- Cross-provider continuity: `../.agents/provider-handoffs/backend-audit.md`

Launch:

```bash
./scripts/crew.sh start backend-audit
```

Role defaults to Codex. Launcher requires Bubblewrap and provisions isolated Codex
Security plugin state plus pinned Bandit, detect-secrets, pip-audit, and Semgrep tools.
Tooling lives under gitignored `.agents/runtime/backend-audit/`, never project venv.
Launcher fails closed if source-read-only enforcement is unavailable.
Run boundary proof after launcher changes:

```bash
./scripts/backend-audit-sandbox.sh self-test
```

Detailed notes, drafts, reports, and proposals are gitignored because unresolved
vulnerability details should not be published with source. Handoff and comms carry
only safe summaries.
