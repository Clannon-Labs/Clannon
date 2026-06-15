# experts/ — domain-specialist sub-agents

Each expert is a real tool-driving agent the orchestrator spawns for deep domain
work. Drop a `@expert`-decorated package here and it self-registers — no wiring.

## NEVER
- Experts NEVER write memory directly (invariant §I.6). The only memory access is
  the READ-ONLY, user-scoped `memory.search` tool; writes happen only via write
  proposals through the Memory Manager.
- Least-privilege: an expert may use ONLY the tools in its `tools=(...)` grant, at
  its declared `permission` — the handler scopes a tool box to exactly those keys.
  Don't grant NETWORK/workspace an expert doesn't need.
- Don't bypass the two-output split: return one `ExpertOutput` (summary +
  full_content + citations + confidence). The handler buffers full findings to
  `ctx.expert_findings` and returns only the brief summary to the orchestrator.
- Input is the expert's structured `input_schema`, never free-form text. Behavior
  lives in the co-located `system.md` (+ on-demand `skills/`), not hardcoded in
  `expert.py`.

## Conventions
- Metadata on the class: `name`, `domain`, `description`, `input_schema`,
  `output_schema=ExpertOutput`, `skills`, `tools`, `model_role`, `permission`, `tags`.
  `run()` builds the per-call task, then calls `think(env, task)`.
- `system.md` + skills resolve overlay-first (`prompts.secure/experts/<name>/…`);
  the committed copies are baselines (expert prompts are UNLOCKED). Skills use
  progressive disclosure — only name + description up front, body via `load_skill`.
- A per-run Docker workspace is created only for experts granted a workspace tool,
  and torn down at run end; uploaded input files are seeded into it.
- Before adding an expert: read `docs/architecture/agents/EXPERTS_AND_TOOLS.md`
  (built vs needed), tell the user what you'll add, and wait for confirmation.

## Tests
`tests/roster_experts.py`, `tests/orchestrator_experts.py`, `tests/expert_fallback.py`,
per-expert (e.g. `tests/experts_writer.py`, `tests/media_expert.py`).

## Authoritative docs
`docs/architecture/agents/EXPERTS_AND_TOOLS.md`; `docs/architecture/SYSTEM_ARCHITECTURE.md` → Experts.
