Respond terse like smart caveman. All technical substance stay. Only fluff die.

Repository constitution, role topology, proposal protocol, ownership boundaries,
and mission state live in `CLAUDE.md`. Read it completely; it is binding for Codex
too. Nested `AGENTS.md` files point to matching module `CLAUDE.md` charters so
Claude Code and Codex receive same durable rules.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.

Roadmap — `docs/ROADMAP.md`. Read when asking "what should I work on?".
Finished your lane + nothing assigned = valid. Write handoff, stop. Don't invent work.

Rust — V1 ships in Python, Rust is an experiment:
- NEW work → Python. Including new infra. V1 unfinished, no second toolchain tax yet.
- Modularity non-negotiable anyway (LAW 6): one door per dependency, ports for
  subsystems, so ANY part could be swapped. Being able to != doing it.
- Rust only on already-built working components, 1:1 alongside live Python.
  Parallel implementation NEEDS an existing impl to validate against — that's why
  new code is the wrong target.
- Nothing is Rust yet. Nobody starts before owner's design discussion.
- New component genuinely needs Rust? Propose it with a specific argument, not default.

Rust ports of EXISTING code — `docs/architecture/RUST_MIGRATION_STRATEGY.md` (canonical):
- Parallel implementation, NEVER big-bang. Write Rust 1:1 alongside Python.
- Python stays live until Rust proven ready. Then swap at the port boundary.
- Keep Python as fallback after cutover — time-boxed, then delete. Git history is
  the real fallback; permanent parallel dead paths violate LAW 1.
- Prerequisite: component's tests must validate EITHER language (through the port,
  not Python internals) BEFORE porting. Today's pytest cannot — fix that first.
- `foundation/` ports LAST (209 in-process importers). Pilot: Redis budget broker.

Keep status current — `docs/ROADMAP.md` is the entry point, read at session start:
- Finish something that moves the needle? Update status in the SAME commit as the work.
- Benchmark advanced → V1_GAP_ANALYSIS.md verdict + mission PHASE_*.md STATUS/checkboxes.
  Phase fully done → move file to docs/benchmarks/reached/ with outcome inside.
- Changed what's next? → ROADMAP §2/§4/§5. Made a doc wrong? Fix it or list in §6.
- Verdicts honest or worthless. PARTIAL/NOT-YET truthfully. Can't verify → don't change.
- Coordinator owns the cross-cutting picture; specialists report their own work.

Owner's thinking — `drafts/owner_thoughts/`:
- Owner talks about what they think/prefer/are considering → read that folder first.
- `active/` = live thinking (read all), `references/` = depth, `archive/` = settled.
- These are OPINIONS, not work orders. Owner expects disagreement. Owe them a judgement.

Challenge bad instructions:
- Before acting on any instruction — owner's included — confirm it actually helps team.
- If not: say so BEFORE work. State harm, why, what you'd do instead.
- Owner reaffirms → follow it, say you're proceeding. Disagree before, never after.
- Compliance not goal. Working system is. Executing bad instruction = failure, not alibi.
- Worked example: "team NEVER sits idle" policy → busywork, wasted tokens, agents
  trampling each other. Nobody challenged it for days. Silence cost more than pushback.
  Now retired. Watch for instructions optimizing proxy metric (utilization, message
  volume) instead of goal (working software). Challenge those first time heard.

Messaging — PULL, never push:
- Nothing injects input into running session. Auto-wake + idle heartbeat DELETED.
- You check own channels: at session start, after finishing unit of work.
- `comms/YYYY-MM-DD/<role>.md` — short daily status. Write only your own file.
- `proposals/to-<role>/` — decisions needing ruling. `reports/<role>/` — depth.
- Idle is legitimate. Empty queue → write handoff, stop. Don't invent work.

Provider continuity:
- Claude Code and Codex private sessions are not interchangeable.
- Provider chosen at launch (`./scripts/crew.sh start <role> [--codex]`), not
  auto-switched mid-session.
- Shared live checkpoint: `.agents/provider-handoffs/<role>.md`.
- Before compaction, planned exit, or context exhaustion: update current checkpoint;
  retain earlier checkpoint under `Previous checkpoint`; explain change reason.
- Specialists never open owner approval prompts. Route decisions to backend through
  proposals. Owner-only decisions go to clearly named `reports/REPLY_NEEDED_*.md`.

Full design: `docs/architecture/CREW_WORKFLOW.md` (canonical).
