# ⚖️ THE CODING LAWS — Clannon

> **This folder is the constitution of the codebase. `LAW/README.md` is the single canonical
> text — central, tracked, and above every other doc.** Every agent (backend/root, memory,
> orchestration, frontend) and every human, every session, every change, obeys it.
>
> **These are LAWS, not guidelines.** You do not weigh a law against convenience — the law wins.
> Before any change lands, check it against ALL of them. A violation you find is **fixed, or
> explicitly FLAGGED to the owner** — it is never silently left. Writing code that breaks a law
> "just for now" is not allowed; if a law genuinely blocks you, you STOP and flag it, you do not
> route around it.
>
> Owner-authored; maintained as the codebase's highest authority. If a per-module `CLAUDE.md`,
> a comment, or a habit conflicts with a law here, **this wins** — fix the other thing.

---

## How to read a law

Each law below is written as: the **Principle** (the one-line rule), **Why** (what it protects —
so you apply the spirit, not just the letter), the **Rules** (concrete + enforceable), **In
practice** (what compliance and violation actually look like in this repo), and a **Self-check**
(the question to ask before you commit). Read the self-checks before every commit — they are the
fastest way to catch a violation while it is still cheap.

---

## LAW 1 — MODULARITY · one source of truth, zero redundancy

**Principle.** One source of truth. One function = one job. One file = one *kind* of job. One
folder = one layer (or that layer's utilities). No duplicate or parallel paths — ever.

**Why.** Redundancy is where bugs breed and drift begins: two copies of a rule agree today and
silently disagree next month, and a reader can't tell which is authoritative. One home means one
place to change a behavior, one place to optimize it, one place to secure it. Modularity is not
tidiness — it is how the system stays correct as it grows.

**Rules.**
1. **No redundant code, anywhere.** If two places do the same thing, consolidate to ONE and have
   the other call it. A copy-pasted block is a bug waiting to happen — fix it on sight.
2. **One function = one job.** If a function does two things, split it. A function's name should
   fully describe what it does; if the honest name needs an "and," split it.
3. **One file = one KIND of job.** A file holds one coherent responsibility (one type, one
   concern), not a grab-bag. Single-stage types live in that stage, not in the shared seam.
4. **One directory = one layer** (memory, verifier, orchestrator, security, api, delivery, config,
   …) or that layer's utilities. Nothing lives in the wrong layer.
5. **A new thing goes in its correct existing home.** You do NOT create a parallel or duplicate
   path because it's faster right now. No speculative surface area — don't add an abstraction,
   file, or path you don't need *yet* (build it when the need is real, in its right home).
6. **Delete dead code.** Unreachable code, commented-out blocks, and "might need it later"
   scaffolding are redundancy too — remove them; git remembers.

**In practice.** *Compliance:* a shared helper called from N sites; a single `derive_record()`
reused, not re-derived. *Violation:* the same string transform computed ad-hoc in `api/config.py`
*and* on `CapabilitySpec.label` — two implementations that agree by luck (a real one we fixed;
that's exactly the shape to hunt).

**Self-check.** *Could I change this behavior in exactly one place? Is there a second
implementation of this rule that only agrees by coincidence? Am I adding a path I don't need yet?*

---

## LAW 2 — READABILITY · a developer must LOVE reading it

**Principle.** Any developer opening the code finds it intuitive: the *why* is explained, naming
is precise, structure is obvious. **Soft cap 500 lines per file (aim ~400).** Short,
single-purpose functions. The codebase reads as if one careful author wrote all of it.

**Why.** Code is read far more than it is written — by the next developer, by a future you, by
the next agent. Unreadable code is unsafe code: people change what they don't understand and break
it. Loving the code is not sentiment; it's the measure of whether the next person can safely
extend it.

**Rules.**
1. **Explain the *why*, not the *what*.** Comments and docstrings teach the reasoning a reader
   can't recover from the code (the tradeoff, the invariant, the gotcha). Never restate what the
   line already says.
2. **Naming is precise.** A name says exactly what the thing is/does. No `data`, `tmp`, `handle2`.
   Rename the moment a name stops being true.
3. **No long files.** 500 lines is a soft cap, and you only approach it when cutting below would
   genuinely hurt clarity; otherwise stay well under (~400). A file growing past this is a signal
   to split by responsibility — do it before the sprawl, not after. > Recent law update by owner.
4. **No long functions.** A function stays short and single-purpose; extract helpers before it
   sprawls. Deep nesting is a smell — flatten with early returns / guard clauses.
5. **Match the surrounding idiom** — comment density, naming style, structure — so the file reads
   as one author's work, not a patchwork.
6. **Public surfaces are documented.** Every exported type/function/endpoint has a docstring that
   tells a caller what it does, what it guarantees, and how it fails.

**In practice.** *Compliance:* a 280-line stage file where each function name tells the story and
the one non-obvious branch has a two-line "why." *Violation:* a 700-line god-file, or a comment
that says `# increment i` above `i += 1`.

**Self-check.** *Would a new developer love opening this file and know where everything is? Do my
comments teach the why, or restate the what? Is any file over 500 lines or any function doing more
than one thing?*

---

## LAW 3 — SPEED · Flow/foundation is the SPINE, and the pipeline runs from ONE place

**Principle.** The code is blazingly fast — no wasted work, everything bounded. `foundation/` +
`Flow` is the circulatory system of the backend, **not** just a feature: **if Flow/foundation can
carry or do something, it MUST — nothing else takes Flow's job.** And **the pipeline runs from
exactly one place: `core/pipeline.py`.**

**Why.** Speed is a product feature users feel on every request. One spine means one place to
optimize, one place to secure, one transport to reason about — side-channels fragment the system,
slow it, and leak. One pipeline driver means the sequence of security + processing stages exists
in a single auditable place; a second stepper is a second thing to keep correct and secure, and
they *will* drift.

**Rules.**
1. **No wasted work.** No redundant passes, no re-reading/re-computing what's already in hand, no
   N+1 loops. Do the work once and pass the result along the spine.
2. **Everything is bounded.** Timeouts, hop caps, loop caps, size caps, token/whole-turn budgets —
   nothing runs unbounded. An unbounded loop or query is a Law-3 *and* Law-5 violation.
3. **Flow is the sole inter-stage transport.** Cross-stage payloads, context, shared contracts,
   and vocabulary all ride `Flow`/`foundation`. No side-channel passing state between stages.
4. **ONE pipeline driver.** `core/pipeline.py` is the ONLY module that steps the stage chain.
   Every entry point (api, cli, tooling, a test that drives a turn) calls `pipeline.run()` —
   nothing else re-walks or re-implements the stages. A second place stepping the pipeline is a
   violation to consolidate immediately.

**In practice.** *Compliance:* an entry point that calls `pipeline.run()` and reads the result.
*Violation:* an endpoint that re-implements "verify → orchestrate → filter" inline, or a stage
that stashes state in a module global instead of on `Flow`.

**Self-check.** *Is there any wasted or repeated work here? Is anything unbounded? Does any state
cross a stage boundary outside Flow? Does anything step the pipeline other than `pipeline.run()`?*

---

## LAW 4 — SECURITY & PRIVACY · the backend governs; config is central, single-source, and private

**Principle.** The backend GOVERNS the frontend: a bypassed, tampered, or hacked client gains **no
privilege** — the backend re-checks identity, authorization, and validity on every request and
refuses anything outside the exposed-for-users set. **All business configuration lives in ONE
central `config/` — the owner's control panel — single-source and private.**

**Why.** The frontend is untrusted by definition (the user controls it). Security that lives in
the client is not security. And configuration is the owner's steering wheel for the product +
often carries secrets — it must be one authoritative place the owner controls, never scattered and
never leaked to a user.

**Rules.**
1. **Central config = the owner's control panel.** Every *business* value the owner might tune —
   plans, tiers, pricing, quotas/limits, feature flags, model choices, defaults — lives in ONE
   central **`config/`** directory. From there the owner can change any business value in one
   place. *Technical* config (timeouts, caps, buffer sizes) may stay in `foundation/` for now.
2. **Single source per concern.** Each changeable-value kind has exactly ONE config file (models →
   `config/models.yaml`, and so on). **No configuration logic lives outside `config/`** — to
   change a value, the owner edits one place. No hardcoded business values scattered in code.
3. **Config is private.** No code path — especially `api/` — exposes config *contents* or lets
   anything outside the owner's own channel read or change it. `GET /config` may return only what a
   client legitimately needs (feature availability, public limits), never the config itself.
4. **The backend governs the frontend.** Identity is set ONCE from a trusted source (the session),
   never from a request body/path/client value, and travels as the sole downstream identity. Every
   resource is authorized by its own ownership row (a foreign id → 404, never a cross-tenant
   read/write). Only harmless, use-case-natural, explicitly-exposed fields are mutable from the
   client; everything else is refused server-side — structurally, not by trusting the frontend.
5. **`api/` is the most exposed surface — scrutinize it hardest.** Never trust a value from the
   request body, path, or client for anything security-bearing. Fail closed on any doubt.
6. **No secrets in code, logs, or responses** (also Law 5) — secrets come from the environment /
   the private config, never committed, never logged, never returned to a client.

**In practice.** *Compliance:* an artifact download authorized by the run's own ownership row (404
otherwise); a settings write that 403s a locked role and 422s an out-of-set value. *Violation:* a
business limit hardcoded in three handlers; a `/config` endpoint that returns the raw config; an
endpoint that trusts `body.user_id`.

**Self-check.** *If the frontend were fully hacked, could it change anything a normal user can't?
Is every business value in the central `config/`? Does `api/` ever trust a client value, or leak
config/secrets?*

---

## LAW 5 — PRODUCTION-GRADE BY DEFAULT · do what real systems do, even unlisted

**Principle.** This ships to real users and real money. Do what a serious production system does
even when no one wrote it down: fail closed, least privilege, bounded resources, honest
degradation, no secret leakage.

**Why.** Half-measures cost trust, money, and security the moment real traffic hits. "It works on
the happy path" is not done; production is defined by what happens when things go wrong.

**Rules.**
1. **Fail closed.** On any fault or uncertainty, deny/stop — never fail open into an unsafe or
   unpaid state. A security check that errors BLOCKS; a budget check that can't reach its store
   refuses the spend.
2. **Least privilege everywhere.** Every component gets the minimum grant it needs — no ambient
   authority, no "it's easier to just allow everything."
3. **Bounded resources.** Timeouts, hop/loop caps, size caps, budgets — enforced, not hoped.
4. **Identity set once, from a trusted source** (see Law 4), never re-derived from content or
   model output.
5. **Idempotency where it matters** — a retried write/settle must not double-apply.
6. **No secrets in code, logs, or client responses.** Ever.
7. **Degrade honestly — never fake success.** If something is unavailable, say so and degrade
   visibly (an honest empty result, a clear error), never a fabricated OK. (This is the runtime
   twin of Law 6's honest tests.)
8. **Typed, structured errors — never swallowed.** Raise specific errors carrying context; never
   catch-and-ignore. Observability without leaking internals to clients.

**Self-check.** *What happens here on failure — does it fail closed? Is anything unbounded or
over-privileged? Could a secret reach a log or a response? If a dependency is down, do I degrade
honestly or fake an OK?*

---

## LAW 6 — REPLACEABILITY · every dependency lives in exactly one swappable place  *(owner instruction, 2026-07-27)*

**Any framework, library, or architectural choice must be replaceable by editing ONE folder, without
looking outside it.** If we ever decline to rewrite something, that must be because we judged the
rewrite wouldn't improve it — **never because we couldn't do it without risking a break.**

This is the owner's bar, in their words:

> "if I am importing any framework or library or using any concept in any part, I should be able to
> swap that part out of the codebase and replace with new, without even having to look outside that
> part."

> "if we didn't rewrite it, it should be because we didn't think it would make it better, not that
> we couldn't do it without risking breaking anything."

### The enforceable rules

1. **One door per dependency.** A third-party framework is imported in exactly ONE module, and that
   module's `CLAUDE.md` says so as a NEVER-line. The worked example already in the tree:
   `core/llm/` — *"the ONLY module in the repo that may import `pydantic_ai`."* Callers pass neutral
   types and get neutral types back; no SDK object escapes the door.
2. **Ports, not imports, across a boundary.** A subsystem another layer depends on is reached
   through a contract in `foundation/contracts/` (`MemoryPort`, `GraphPort`, `BudgetPort`,
   `ArtifactStore`). Consumer and implementer must not import each other. This is what makes a
   swap — to another library, another architecture, or **another language** — a local change.
3. **A boundary must own its guarantees.** *(Added from a live incident — see below.)* If an
   invariant we care about is enforced only by the thing on the far side of a port, we have not
   isolated a dependency; we have outsourced a promise. Every bound the system relies on
   (spend ceilings, loop caps, timeouts, fail-closed gates) needs enforcement **we** own. A
   third-party limiter is defence in depth, never the guarantee.
4. **Language-agnostic by construction.** A port must be swappable for an implementation in another
   language (Rust, C) without callers changing. In practice: keep port surfaces narrow and their
   types plain; do not let language-specific richness leak into a contract.

### Why rule 3 exists — this actually happened

`requirements.txt` declared a bare `pydantic-ai`. CI resolved 2.18.0 against the proven 2.4.0, and
the orchestrator loop ran **64 model calls against a bound of 22**. That bound is the runaway-loop
money guard — and `usage_limits_for_layer` merely constructed a `UsageLimits(request_limit=N)` and
handed it to the library. We never counted requests ourselves.

The swap *boundary* held perfectly: pydantic-ai is confined to one module and could be replaced from
there. The **guarantee** did not. A dependency upgrade silently removed a spend ceiling, and only a
test caught it. Rule 1 alone would have called this architecture compliant. It wasn't.

### Pre-commit self-check for this law

- Is every third-party import for this dependency inside its ONE owning module?
- Could I swap this library/architecture out by editing only that folder — honestly, without
  grepping the rest of the tree?
- Does any invariant here depend on third-party code to be enforced? If yes, do we enforce it
  ourselves too?
- If someone reimplemented this behind the same port in another language, would any caller need to
  change?

## LAW 7 — PROVE IT · tests are first-class, and verification is honest  *(extension — flag if you'd scope it differently)*

**Principle.** Every behavior is **proven by a test**, not asserted by hope. The full suite is
**green before every commit**. Tests — and benchmarks — are **honest**: they never fake a pass,
and they report gaps (PARTIAL / NOT-YET) truthfully.

**Why.** Untested code is a claim, not a fact. Worse, a *fake-green* test is more dangerous than no
test — it hides the gap behind a comforting checkmark. This codebase's benchmarks measure real
capability precisely because they refuse to fake a pass; that same honesty is law for all tests.
(Added as its own law because verification discipline is distinct from runtime robustness (Law 5)
and is central to how this project earns trust — trim or fold it back into Law 5 if you prefer.)

**Rules.**
1. **Prove each behavior with a test** — including the failure path, not just the happy path. A
   bug fix ships with a regression test that fails before the fix and passes after.
2. **Suite green before EVERY commit.** No exceptions. Never pipe the test run through `tail` in an
   `&&` chain (it hides the real exit code). And **verify green before every push**, including
   "doc-only" ones (a doc-only change can still sweep in code — verify).
3. **Tests are honest.** Never assert what you didn't actually verify. Never weaken a test to make
   it pass. A benchmark reports PARTIAL / NOT-YET truthfully rather than embedding a fabricated
   green — if a test genuinely can't verify something (e.g. a live-LLM detection offline), it says
   so honestly instead of pretending.
4. **A green you didn't run is not a green.** Don't claim passing tests you didn't execute.

**Self-check.** *Is this behavior proven, or hoped? Does the test cover the failure path? Is the
green real — did I run it? Am I reporting the honest verdict, or a comfortable one?*

---

## The pre-commit self-check (run this every time, on every change)

1. **Modularity** — one source of truth, no duplicate/parallel path, right home, nothing dead? (L1)
2. **Readability** — intuitive, *why* explained, ≤500 lines, short single-purpose functions? (L2)
3. **Speed/spine** — no wasted work, bounded, Flow-only transport, one pipeline driver? (L3)
4. **Security/config** — backend governs, business config central+private, `api/` trusts nothing? (L4)
5. **Production-grade** — fail-closed, least-privilege, no secret leak, degrades honestly? (L5)
6. **Replaceable** — dependency behind ONE door, swappable from one folder, and do we own our own
   guarantees rather than trusting the library's? (L6)
7. **Proven** — tests for it (incl. failure path), suite green, honestly reported? (L7)

If any answer is "no," you fix it or you flag it to the owner. You do not land it and hope.

## How the laws are enforced

- **Always in view.** The top of the root `CLAUDE.md` and every per-module `CLAUDE.md` carries a
  crisp law banner pointing here — so no agent works without the laws in front of them, every
  session, without the full text being duplicated everywhere.
- **Per change.** The pre-commit self-check above runs before every commit.
- **Cross-agent.** Any contract/security/structural change is propose-first; the receiver checks it
  against these laws before accepting.
- **This document is the authority.** Extend it only in the owner's direction; when in doubt, ask.
</content>
