# prompts.secure/ — the real (hardened) prompts for every LLM call

This folder is **never committed** (gitignored). It holds the production text for
**every** prompt the system feeds an LLM. The committed `prompts/*/system.md` and
`experts/*/system.md` (+ skills) in the repo are only **dev/CI baselines**; when a
file here exists it overrides the matching baseline, and anything missing here
falls back to the baseline.

## How it's found (zero config)

The loader (`registry/config/prompts.py` → `overlay_root()`) looks, in order:

1. `VRAKSHA_PROMPTS_DIR` env var, if set (explicit override).
2. An auto-discovered `prompts.secure/` next to where the agent runs (CWD) or
   beside the code (repo root). **Just drop this folder there and it works.**
3. Nothing → the committed baselines.

So in production you upload **this whole folder** to the app root. No other config.
Set `VRAKSHA_REQUIRE_PROD_PROMPTS=1` there so boot fails closed if a security
prompt (verifier, filter) is somehow missing here and would ride its baseline.

## Layout (mirrors the repo tree)

```
prompts.secure/
  verifier/system.md        # locked security boundary (input content blocker)
  filter/system.md          # locked security boundary (output gate)
  orchestrator/system.md    # tool-driving / decision logic
  memory/system.md          # memory-distillation agent
  experts/
    web_research/system.md
    web_research/skills/source_eval.md
    writer/system.md
    writer/skills/brief_structure.md
    writer/skills/client_report.md
```

## Rules

- The **manifest** (`prompts/registry.yaml`) and every `locked` flag are always
  read from the repo, never from here — this folder supplies **content only**. It
  can harden a prompt or skill but can **never** un-lock one or add a new
  prompt/skill (the set is fixed by the repo).
- These files currently start as copies of the baselines. **Edit them here to
  harden** — this is the safe place; your edits never touch git.
