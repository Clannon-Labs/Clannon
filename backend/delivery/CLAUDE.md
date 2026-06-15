# delivery/ — the final hand-off to the user's platform (UI-agnostic)

Owns the last stage: set `ctx.final_response` and deliver via the active adapter.

## NEVER
- Platform adapters do NOT own reasoning. They translate messages / actions /
  notifications / delivery-state into Vraksha's internal contracts — no LLM calls,
  no business decisions here (cheap formatting only).
- The decision log streams DIRECTLY to the client; only the final report has passed
  the output filter before this stage. Don't re-filter the log; don't emit a final
  response the filter hasn't accepted.
- MCP / external sources, when added, enter the pipeline as normalized input through
  the SAME sanitization + verification gates — they never bypass the security stages.

## Conventions
- UI-agnostic core. The checkpoint adapter is the CLI (`_deliver_cli` prints the
  streamed decision log, then the filtered answer; `VRAKSHA_CLI_QUIET=1` suppresses
  the dump for interactive/server use). A frontend connects the same way: drain the
  decision-log queue, render the final response — no change to this core (the live
  server adapter / SSE lives in `api/runs.py`).
- Session state is platform-agnostic (Redis, planned): a user can start a task on
  web and receive the result on another channel without session discontinuity.

## Tests
`tests/delivery_stage.py`.

## Authoritative docs
`docs/architecture/SYSTEM_ARCHITECTURE.md` → Platform Delivery; `api/README.md` (SSE adapter).
