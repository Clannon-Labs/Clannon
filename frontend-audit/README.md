# Frontend Audit role

Independent source-read-only product-security research role.

- Charter: `CLAUDE.md` (`AGENTS.md` points Codex to the same source)
- Domain threat model: `../frontend/FRONTEND_AUDIT_CHARTER.md`
- Safe durable template: `../.agents/templates/AUDIT_FINDING.md`
- Local research: `notes/`, `drafts/`
- Deep audits: `../reports/frontend-audit/report_vN.md`
- Frontend-owned findings: `../proposals/to-frontend/from-frontend-audit/`
- Backend-owned findings: `../proposals/to-backend/from-frontend-audit/`
- Cross-provider continuity: `../.agents/provider-handoffs/frontend-audit.md`

Launch:

```bash
./scripts/crew.sh start frontend-audit           # Claude Code (default)
./scripts/crew.sh start frontend-audit --codex   # Codex
```

Both providers use `scripts/audit-sandbox.sh`. Bubblewrap mounts repository source,
Git metadata, dependency manifests, lockfiles, project `node_modules`, and this role's
own rules read-only. Only explicit evidence and continuity outputs are writable.
Missing enforcement refuses launch.

Pinned Semgrep and detect-secrets live under gitignored
`.agents/runtime/frontend-audit/tools-venv/`. Pinned npm, ESLint, TypeScript, Vitest,
and Playwright packages live under `.agents/runtime/frontend-audit/node-tools/`.
Neither environment changes `frontend/package.json`, its lockfile, its
`node_modules`, or a contributor's global tools.

Provider equipment:

- Codex: Codex Security plugin, configured by `codex.config.toml`.
- Claude: `.claude/settings.json` plus `.claude/skills/audit-scanners/`; shared
  `attack-path-tracer` and `counterevidence` agents live in root `.claude/agents/`.

Run boundary proof after launcher, role-policy, or tooling changes:

```bash
./scripts/audit-sandbox.sh frontend-audit self-test --claude
./scripts/audit-sandbox.sh frontend-audit self-test --codex
```

Detailed notes, drafts, reports, and proposals are gitignored because unresolved
vulnerability detail should not publish with source. Handoff and comms contain safe
summaries only.
