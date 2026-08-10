---
name: audit-scanners
description: The exact no-fix invocations of the auditor's pinned scanners (bandit, semgrep, detect-secrets, pip-audit) inside the sandbox, plus how to read their output as evidence. Use whenever a scan is part of an audit — baseline, deep, or diff — so a run is reproducible and cannot silently mutate the tree or the project environment.
---

Scanners are **inputs to an audit, never the audit**. A clean run is evidence about
one narrow question the tool asks; it is not a verdict, and it never justifies PASS
(`../CLAUDE.md` — Reporting contract).

## Where the tools come from

They are on `PATH` already, from the auditor's isolated environment under
`.agents/runtime/backend-audit/tools-venv/` — provisioned and pinned by
`scripts/backend-audit-sandbox.sh` from `../tooling-requirements.txt`.

Never `pip install` anything, never touch `backend/.venv`, never run a tool's fix
mode. The sandbox mounts the tree read-only and the project's permission rules deny
the installers outright — if a command is refused, that is the design working, not
an obstacle to route around.

## Pin the revision before the first scan

```bash
git -C .. rev-parse HEAD          # goes in the report header, and in every finding
git -C .. status --porcelain      # a dirty tree makes the revision meaningless — say so
```

## The invocations

Run from the role directory (`backend-audit/`). Write output into `notes/` — it is
one of the few writable paths, and raw scanner output is unresolved detail that
stays gitignored.

```bash
# Python SAST. Excludes tests and the project venv: findings there are noise.
bandit -q -r ../backend -x ../backend/tests,../backend/.venv \
  -f json -o notes/$(date +%F)-bandit.json

# Rule-based SAST. Registry rulesets need the network, which the sandbox has.
# NEVER --autofix: this role does not edit code.
semgrep scan --metrics off --config p/security-audit --config p/python \
  --json --output notes/$(date +%F)-semgrep.json ../backend

# Secrets. `scan` only — `audit` is an interactive baseline editor, and editing a
# baseline is changing the repo's security posture, which is not this role's call.
detect-secrets scan --all-files ../backend > notes/$(date +%F)-secrets.json

# Dependency CVEs. Read the manifests; never resolve into a project environment.
pip-audit --requirement ../backend/requirements.txt --progress-spinner off
pip-audit --requirement ../backend/requirements-dev.txt --progress-spinner off
```

For a **diff scan**, scope by the changed files rather than re-running everything:

```bash
git -C .. diff --name-only <base>..HEAD -- backend/ | sed 's|^|../|' > notes/changed.txt
semgrep scan --metrics off --config p/security-audit --json \
  --output notes/$(date +%F)-semgrep-diff.json $(cat notes/changed.txt)
```

A diff scan complements a periodic full review; it never replaces one.

## Reading the output

- **Every hit is a hypothesis.** Open the file and the call site before it becomes
  a finding. Confirm reachability from an attacker-controlled source — an
  unreachable pattern match is not a vulnerability.
- **Every miss is a hypothesis too.** These tools find pattern-shaped bugs. They do
  not find broken authorization, tenant mixing, confused deputies, TOCTOU, economic
  abuse, or a design that is unsafe only under a condition — which is where this
  role's real value is.
- **Suppressions and exclusions are part of the result.** Record what you excluded
  (tests, venv, generated code) in the report's deferred-surfaces section; an
  exclusion nobody wrote down is a coverage lie.
- **Version-pin the claim.** Cite the tool versions (`bandit --version`, etc.) with
  the finding, so a retest can reproduce it.
