"""Expert implementations. Each expert package self-registers with the capability
registry (`@expert` from `registry`) on import; the calling door + run environment
live in `registry.capabilities.handler` (Capabilities, ExpertEnv, think).

To add an expert, drop a folder here — no other wiring:

    experts/<name>/
      expert.py   — input_schema + a class subclassing `Expert` (from
                    registry.capabilities.handler) that sets name, domain,
                    description, input_schema, skills, and (optional) tools,
                    model_role, permission, tags. Override render() only for richer
                    input. Most experts add no run().
      system.md   — baseline behavior prompt (committed fallback).
      skills/     — baseline skill .md files, loaded on demand.
    prompts.secure/experts/<name>/  — the hardened system.md + skills/ overlay.

The expert is a self-contained tool-driving agent: it declares what it needs, the
handler equips it, and the model does the work over its system prompt + skills +
granted tools. See the `Expert` base class docstring for the full recipe."""
