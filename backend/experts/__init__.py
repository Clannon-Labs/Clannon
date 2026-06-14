"""Expert implementations. Each expert package self-registers with the capability
registry (`@expert` from `registry`) on import; the calling door + run environment
live in `registry.capabilities.handler` (Capabilities, ExpertEnv, think).

To add an expert, drop a folder here — no other wiring. Every expert.py has the
SAME uniform shape (an input_schema, the declarations, one entry-point `run()`, and
a `_task()` util); only the declarations and `_task()` differ per expert:

    experts/<name>/
      expert.py   — input_schema (pydantic) + an @expert class declaring: name,
                    domain, description, input_schema, output_schema=ExpertOutput,
                    skills, and (optional) tools, model_role, permission, tags. The
                    tools you name are REQUESTED; the handler grants them (scoped +
                    guarded). The entry point is always:
                        async def run(self, args, env): return await think(env, _task(args, env))
                    and `_task(args, env)` (a module util) builds the per-call task
                    text from the structured input (richer inputs — e.g. inlining
                    attached findings — go in `_task`/helpers, never in run()).
      system.md   — baseline behavior prompt (committed fallback).
      skills/     — baseline skill .md files, loaded on demand.
    prompts.secure/experts/<name>/  — the hardened system.md + skills/ overlay.

The expert is a self-contained tool-driving agent: it declares what it needs, the
handler equips it (ExpertEnv), and the model does the work itself over its system
prompt + skills + granted tools, returning the structured ExpertOutput."""
