---
description: Fast grep-based audit of the import/scope invariants the CI Semgrep gate is supposed to enforce but doesn't yet exist. Run before committing changes that touch boundaries.
allowed-tools: Bash, Read, Grep
---

Run the checks below from the repo root and report a concise PASS/FAIL per check
with offending `file:line` for any hit. This is a deterministic stand-in for the
not-yet-built CI scope/import gate (`docs/architecture/INVARIANT_OWNERSHIP.md` §V.20) —
a hit is a likely invariant violation to investigate, not always a confirmed bug.

Scope to the current change when one exists (`git diff --name-only main...HEAD`),
otherwise scan the whole `backend/` tree. Use ripgrep.

1. **pydantic_ai confined to core/llm** (invariant §III.12):
   `rg -n "import pydantic_ai|from pydantic_ai" backend --glob '!backend/core/llm/**' --glob '!backend/tests/**'`
   — any hit FAILS.

2. **Memory internals not imported outside core/memory** (§V.20):
   `rg -n "from core.memory import (store|embeddings|writer)|core\.memory\.(store|embeddings|writer)" backend --glob '!backend/core/memory/**'`
   — any hit FAILS.

3. **foundation imports nothing upward** (§III, dep direction):
   `rg -n "^\s*(from|import) (core|security|registry|experts|tools|api|delivery)" backend/foundation`
   — any hit FAILS.

4. **No connection-level Postgres SET** (§V.22 — must be `SET LOCAL` in a txn):
   `rg -n "\bSET\b(?!\s+LOCAL)" backend --glob '*.py' -i | rg -i "set .*=|set role|set search_path"`
   — review each hit; a bare `SET` for tenant scope FAILS.

5. **NETWORK tools route through the SSRF gate**: for each tool declaring
   `permission = PermissionLevel.NETWORK` (`rg -n "PermissionLevel.NETWORK" backend/tools`),
   confirm it calls `validate_public_url`. A NETWORK tool that makes an HTTP call
   without the gate FAILS.

6. **Deep-import of foundation** (use the package surface):
   `rg -n "from foundation\.(transport|vocab|contracts)" backend --glob '!backend/foundation/**'`
   — hits are a smell (prefer `from foundation import X`); report as WARN.

Then run the suite if the change is non-trivial:
`cd backend && python -m pytest tests/ -q` (note any skips — real model/Docker/ClamAV
tests skip without those services).

Summarize: per-check PASS/FAIL/WARN, the offending lines, and a one-line overall verdict.
