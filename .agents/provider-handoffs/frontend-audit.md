# Shared provider handoff — frontend-audit

Independent source-read-only frontend product-security research role. Read
`frontend-audit/CLAUDE.md`, then the code-grounded threat model in
`frontend/FRONTEND_AUDIT_CHARTER.md`, after root boot files. Detailed unresolved
findings stay in gitignored reports and proposals; this tracked file carries safe
continuity only.

## Current checkpoint — role ready; baseline audit not started (2026-08-10)

Role architecture and Bubblewrap boundary exist for Claude Code and Codex. Every
launch goes through one role-parameterized `scripts/audit-sandbox.sh`; Claude is
default, Codex explicit with `--codex`. Source, `.git`, manifests, lockfiles, project
`node_modules`, and role rules are read-only. Only notes, drafts, reports, own comms,
handoff, and routed proposal outputs are writable.

Exact isolated tooling is coordinator-owned and lock-pinned: Semgrep 1.172.0,
detect-secrets 1.5.0, npm 11.16.0, ESLint 9.39.4, eslint-config-next 16.2.12,
TypeScript 5.9.3, Vitest 4.1.9, and Playwright 1.62.0. Never install or update tools
inside the role. Codex also has Codex Security; Claude has the repo-local scanner skill
plus shared attack-path and counterevidence agents.

First work: pin revision and dirty state; refresh the frontend charter's threat model
against live code; run a standard baseline; then prioritize reachable browser/client
abuse paths. Two charter seeds require verification, not repetition as findings:
blob/PDF iframe isolation and markdown-link scheme handling. Seek counterevidence and
read backend implementation before any claim that a server-side control is absent.

No security verdict exists. No candidate risk is a finding yet.

## Change note

Role created from frontend specialist's code-grounded charter. Independent audit lane
separates adversarial research from implementation while structural sandboxing prevents
self-remediation, source mutation, Git mutation, or remote publishing.
