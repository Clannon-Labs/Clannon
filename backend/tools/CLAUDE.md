# tools/ — deterministic functions (no reasoning)

Each tool is a `@tool`-decorated class that does one concrete thing and returns its
`output_schema`. Drop a file here and it self-registers — no wiring.

## NEVER
- A tool imports ONLY `registry` + `foundation`. It must NOT import memory, expert,
  or orchestrator internals. Tools receive no memory handle. **One sanctioned
  exception:** `web_search.py` imports
  `core.llm.grounded_search` — the same `core.llm`-as-SDK-boundary seam
  `registry/capabilities/handler/__init__.py` already depends on (never
  `pydantic_ai` directly). `scripts/check_invariants.py` models this exact shape
  as expected. Don't treat it as license to reach into `core.llm` for a new tool
  without a conscious call — grounded search blurs the tools-are-deterministic /
  experts-are-LLM-backed line (`core/orchestrator/CLAUDE.md`) on purpose, once,
  as an accepted tradeoff; it is not a precedent to copy silently as the roster
  grows.
- Every network tool validates its URL through the single SSRF gate
  `tools._net.validate_public_url` — on the initial URL AND every redirect hop
  (redirects followed manually, never automatically). Don't write a second copy of
  the rule. The gate blocks non-http(s), embedded credentials, and any host that
  resolves to an internal / loopback / link-local / metadata address.
- Declare the correct `permission`. `NETWORK` tools have their output re-sanitized
  by the handler (invariant A) — don't mislabel a network tool as `READ` to dodge
  it. Read response bodies with `read_capped` (cap on bytes actually received, never
  a trusted Content-Length) + `decode_response` (decode, never execute).
- `wants_workspace` tools run only inside an expert's sandboxed workspace; paths are
  workspace-relative (no absolute, no `..`/symlink escape — enforced by the
  workspace, don't second-guess it).

## Conventions
- Metadata on the class: `name`, `domain`, `description`, `input_schema`,
  `output_schema`, `permission` (default READ), `tags`, optional `timeout_s`.
  Identity key = `f"{domain}.{name}"`. Shared HTTP primitives live in `_net.py`.
- Optional `eager = True` puts the tool on the orchestrator's **hot path** (offered up
  front). Omit it (the default) and the tool **defers** behind tool search — discovered
  on demand, kept out of context until then. Reserve `eager` for the few tools used on
  most turns (today: only web search); situational tools (calculator, fetch, http, etc.)
  stay deferred.
- The handler enforces grants/permission/timeout/cap/sanitize — the tool just does
  the work. Permission levels: READ < NETWORK < WRITE … (see `foundation.PermissionLevel`).

## Tests
`tests/workspace_tools.py`, `tests/memory_tools.py`, `tests/delivery_tools.py`.

## Authoritative docs
`docs/architecture/agents/EXPERTS_AND_TOOLS.md` → Tools; handler in
`registry/capabilities/handler/tools.py`.
