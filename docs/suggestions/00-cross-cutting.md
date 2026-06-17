# Cross-cutting findings

Issues that span more than one domain. These are the highest-leverage fixes because one
change removes coupling in several files at once. Both were verified first-hand.

---

<a id="x1"></a>
## X1 — The pipeline is driven three different ways, two with a hand-synced parallel array

- **Severity:** High
- **Type:** duplication + change-amplifying coupling
- **Locations:**
  - `core/pipeline.py:31` — canonical `ACTIVE_STAGES` list + `run()` using `Flow.chain`
  - `main.py:43` (`_STAGE_LABELS`) and `main.py:164-170` — manual re-walk for the TUI
  - `api/runs.py:56` (`_STAGE_STATUS`) and `api/runs.py:506-513` — manual re-walk for SSE

**Problem.** There is one true source of pipeline order, `ACTIVE_STAGES`. But only
`core.pipeline.run()` actually uses it through `Flow.chain`. The two real entry points —
the CLI/TUI and the API — *don't call `run()`*. They each re-implement the stage loop by
hand so they can observe it:

```python
# main.py:164
for stage, label in zip(pipeline.ACTIVE_STAGES, _STAGE_LABELS):
    if flow.should_stop: break
    ...
    flow = await stage(flow)

# api/runs.py:506
for stage, status in zip(ACTIVE_STAGES, _STAGE_STATUS):
    if flow.should_stop: break
    ...
    flow = await stage(flow)
```

Each copy re-implements the `should_stop` short-circuit that `Flow.chain` already owns,
and each carries a **parallel side-array** (`_STAGE_LABELS`, `_STAGE_STATUS`) that is
positionally coupled to `ACTIVE_STAGES` by nothing but `zip`. Add a stage, reorder a
stage, or remove one, and you must edit `ACTIVE_STAGES` **plus** both side-arrays in two
other files — and if you miss one, the labels silently slip by one stage with no error.

**Why it hurts.** This is precisely the "edit multiple files to change one thing" pain
you called out, applied to the pipeline spine — the most important list in the system.
It will get worse: the cloud build adds more callers (webhooks, batch runs) and each will
be tempted to copy the loop again. The api `CLAUDE.md` even documents *why* this happened
("the server only WRAPS the pipeline and observes it") — the wrapping is legitimate, but
the current way to wrap is "copy the loop."

**Suggestion.** Make observation a first-class parameter of the one driver, so every
caller shares it:

```python
# core/pipeline.py
async def run(raw_input, session_id, user_id="local-user", *,
              on_stage=None,         # called (stage, flow) before each stage runs
              decision_log=None):    # optional sink swapped onto ctx.decision_log
    flow = Flow.new(raw_input, session_id, user_id=user_id)
    if decision_log is not None:
        flow.ctx.decision_log = decision_log
    return await Flow.chain(flow, ACTIVE_STAGES, on_stage=on_stage)
```

Then carry the label/status *with* the stage instead of beside it — one record per stage:

```python
ACTIVE_STAGES = [
    Stage(intake.process,  label="intake",     status="queued"),
    Stage(sanitizer.run,   label="sanitizing", status="sanitizing"),
    ...
]
```

Now the TUI passes `on_stage=lambda s, f: live.update(s.label)` and the API passes
`on_stage=lambda s, f: run.on_status(s.status)`. One list, one loop, observers injected.
Adding a stage is a one-line edit in one file. This also resolves X2 (below), because the
decision-log sink is now passed in rather than re-built per caller.

> Note: `api/runs.py` does one extra thing in its loop — a post-orchestrator hook
> (`if stage.__module__.startswith("core.orchestrator"): run.on_experts_settled(...)`,
> `runs.py:512`). The `on_stage` callback covers this cleanly: the API's callback checks
> the stage identity and fires the hook. No special case needed in core.

---

<a id="x2"></a>
## X2 — `_ObservedLog` is duplicated verbatim

- **Severity:** Medium
- **Type:** duplication
- **Locations:** `main.py:71-80` and `api/runs.py:107-118`

**Problem.** Both files define the same class — a `list` subclass that calls a callback on
every `append` so the decision log can be streamed/mirrored as the run produces it. They
are line-for-line the same idea (the CLI mirrors to the TUI; the API mirrors to SSE).

**Why it hurts.** Any change to how the decision log is observed (e.g. also mirror
`extend`, add backpressure, debounce) has to be made in two places. It's small, but it's
the kind of silent divergence that bites later.

**Suggestion.** Lift one `ObservedLog(list)` into a shared spot both already import —
naturally `foundation.transport` (it's a transport concern: a notifying decision-log
sink), or a tiny `core/observability.py`. Both callers construct it with their callback.
If X1 lands, the sink is passed into `pipeline.run(decision_log=...)` and this dedup falls
out for free.
