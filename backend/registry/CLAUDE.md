# registry/ — the single place anything gets registered

Owns capability registration (tools/experts) + the guarded handler, and the config
loaders (`registry.config`: models + prompts). The base tier config consumers
import directly (`foundation` can't — it imports nothing).

## NEVER
- `@tool` / `@expert` are the ONLY way to register a capability; `discover()`
  imports the packages so the decorators fire. A malformed/duplicate capability
  registers BROKEN (recorded, excluded) — it must never crash discovery. Don't
  hand-maintain a registry list.
- The handler is where the guards live, and they are not optional: caller grants +
  `PermissionLevel`, arg validation against `input_schema`, timeout + output cap,
  and **invariant A** — NETWORK-tool output is re-sanitized (`scan_text`) before it
  can reach reasoning. Don't add a capability path that skips the handler.
- Prompts: the manifest (`prompts/registry.yaml`) and every `locked` flag are
  ALWAYS read from the in-repo `prompts/`, NEVER from the overlay. The overlay
  (`prompts.secure/` or `VRAKSHA_PROMPTS_DIR`) supplies file CONTENT only — it can
  harden a prompt but can NEVER un-lock one or add one. There is NO runtime/end-user
  prompt override — never add a code path that lets request data replace a prompt.
- Sandbox code-exec is OFF unless `VRAKSHA_ENABLE_SANDBOX=1`; the container is
  no-network, non-root, read-only-rootfs, memory/CPU/pids/time-bounded, paths
  confined to the workspace (no `..`/symlink escape). Don't relax those defaults.

## Conventions
- `registry.config` (models/prompts) = base tier. `registry.capabilities` = specs,
  store, registration, and `handler/` (tools, experts, sandbox, support). Capability
  metadata lives on the class — it's the source of truth and drives the Expert→UI
  contract (prefer metadata-driven rendering; avoid manual frontend registration).

## Tests
`tests/orchestrator_registry.py`, `tests/roster_experts.py`, `tests/sandbox_workspace.py`, `tests/prompt_overlay.py`.

## Authoritative docs
`docs/architecture/agents/EXPERTS_AND_TOOLS.md`; `foundation/README.md` → Model & prompt routing;
`prompts.secure/README.md` (overlay).
