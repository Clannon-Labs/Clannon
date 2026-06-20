# HANDOFF

## This run (branch `test/expert-run-contract`)

**Done.** Added an additive conformance test for the shared expert entry-point
contract: `backend/tests/expert_contract.py`.

- Pins that every registered expert exposes
  `async def run(self, args: <input_schema>, env: ExpertEnv) -> ExpertOutput`
  and declares `output_schema = ExpertOutput`. Source of the contract:
  `backend/experts/__init__.py` (docstring) and `backend/experts/CLAUDE.md`
  (Conventions).
- Two tests:
  - `test_expert_roster_matches_files` — enumeration guard: each
    `experts/*/expert.py` registers exactly one non-broken expert (so a divergent
    expert that fails to register can't be silently skipped). Uses
    `experts.__file__` for the dir, so it is cwd-independent.
  - `test_expert_run_conforms_to_shared_contract` — per-expert signature +
    return-shape assertions, collecting all divergences into one message.
- Asserts the live, registered roster via `discover()` + `registry.catalog(...)`,
  so a newly added expert is covered automatically with no edit to the test.

**Reality pinned before writing:** introspected all 9 experts via the venv. All 9
conform (coroutine `run`, params exactly `[self, args, env]`,
`get_type_hints` resolves `args`→input_schema, `env`→ExpertEnv,
`return`→ExpertOutput, `output_schema is ExpertOutput`). 0 broken, 9 `expert.py`
files == 9 registered. No expert diverges, so no `needs-reviewer` issue was
needed. Negative-checked the assertions catch a sync `run`, wrong param names,
and a wrong `output_schema`.

**Did NOT touch:** any expert, the registry, or the handler — test-only.

**Residual risk:** low. The test couples to the `experts/*/expert.py` naming +
one-expert-per-file convention via the enumeration guard; if a future expert is
registered from a differently named module, `test_expert_roster_matches_files`
would flag a count mismatch (intended, surfaces a convention break for a human).
The signature test relies on annotations being present and resolvable; an expert
that drops annotations entirely would be only partially checked by the type-hint
assertions (params/async/output_schema still catch the structural divergence).

## Next (from QUEUE.md)
QUEUE.md tracking is handled externally; the expert-contract task was the last
line. No mid-flight work.
