---
name: audit-scanners
description: Exact no-fix invocations for the frontend auditor's isolated pinned scanners and project-aware JS/TS tools. Use whenever a baseline, deep, or diff audit includes automated checks, so evidence is reproducible without changing project source, manifests, lockfiles, or node_modules.
---

Scanners are evidence inputs, never audit verdicts. A clean run cannot establish
authorization safety, browser trust-boundary safety, or absence of abuse paths.

## Tool provenance

`scripts/audit-sandbox.sh` provisions exact versions from `tooling-requirements.txt`
and `tooling/package-lock.json` into `.agents/runtime/frontend-audit/`. Tools are on
`PATH`; never install, update, fix, or invoke project package-manager scripts.

Pin revision and dirty state first:

```bash
git -C .. rev-parse HEAD
git -C .. status --porcelain
```

Write raw output under `notes/`, never project directories:

```bash
# Pattern SAST. Confirm every result by reading source and proving reachability.
semgrep scan --metrics off --config p/security-audit --config p/typescript \
  --json --output notes/$(date +%F)-semgrep.json ../frontend

# Secret patterns. Scan only; `audit` edits a baseline and is forbidden.
detect-secrets scan --all-files ../frontend > notes/$(date +%F)-secrets.json

# Dependency advisory evidence. `npm audit` reads project lockfile without fixing.
(cd ../frontend && npm audit --package-lock-only --ignore-scripts --json) \
  > notes/$(date +%F)-npm-audit.json

# Project-aware checks. Output and caches stay in writable notes/ or /tmp.
(cd ../frontend && eslint --no-cache .)
(cd ../frontend && tsc --noEmit --pretty false --project tsconfig.json \
  --tsBuildInfoFile /tmp/frontend-audit.tsbuildinfo)
(cd ../frontend && VITE_CONFIG_NATIVE_IGNORE_WARNING=true \
  vitest list --root . --filesOnly --no-color) \
  > notes/$(date +%F)-vitest-files.txt
(cd ../frontend && PLAYWRIGHT_SKIP_WEB_SERVER=1 \
  playwright test --config playwright.config.ts --list --reporter=line) \
  > notes/$(date +%F)-playwright-tests.txt
```

`npm audit` exits nonzero when it reports vulnerabilities. Preserve output and record
the exit status; do not convert findings into a fake-green command.

For diff review, derive changed files from Git and pass only existing TypeScript or
JavaScript files to Semgrep/ESLint. Never use `--autofix`, `--fix`, `npm audit fix`,
snapshot update, or any cache-clean command.

Interpretation:

- Hit = hypothesis until attacker-controlled source, reachable sink, prerequisites,
  and counterevidence are read and tested.
- Miss = evidence only for rules/tool/version/scope actually run.
- Client-side enforcement never proves a security control. Read backend owning route
  before claiming server refusal or absence.
- Record exclusions, versions, command exits, deferred surfaces, and dirty-tree state.
