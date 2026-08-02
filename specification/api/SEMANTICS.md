# What the surfaces MEAN — and what the UI may never claim

`ROUTES.md` says what exists. **This says what it means** — the part you cannot read
off a signature, and the part that has actually caused incidents.

Every rule here is a claim the UI is forbidden to make. None were invented; each is
something that went wrong, or was caught just before it did.

Merged 2026-08-02 from `reports/INTEGRATION_CONTRACT.md` (v1, 2026-07-26). Stale
claims removed and recorded in §7.

> **Deliberately not here:** the SSE event vocabulary and payload shapes.
> `sse_contract_drift.py` checks those against `backend/api/README.md` and the
> frontend fixture. A copy here would be unverified. See `ROUTES.md` §2.

---

## 0. The four rules everything else follows

| # | Rule | Consequence if broken |
|---|---|---|
| 1 | **Live SSE is animation. Persisted REST is authority.** | A seal or memory claim built on a live frame asserts something that may never have persisted |
| 2 | **Backend owns data, identity, authorization, filter truth, persistence. Frontend owns rendering.** | A privilege enforced in the client is not enforced |
| 3 | **Degraded and empty must not render identically to success** — unless the contract says the UI genuinely cannot tell them apart, and then say so out loud | Silent failure looks like a true negative |
| 4 | **No unilateral change to a shared shape.** File in `requests/`; both sides move together | Drift the drift test cannot see |

---

## 1. Hydration MOMENT — a dry run, never evidence

`GET /memory/hydration-preview?brief=<text>&projectId=<id>`

Shows what the memory Manager **would** put in context. Same `MemoryPort.hydrate` door
a real run uses, authenticated `user_id`, real trust/similarity/recency ranking. Max 8,
best first.

| State | What it means |
|---|---|
| Draft empty | No request. Show resting memory from `GET /memory` |
| 1–2 non-whitespace chars | No request. Listening locally |
| Loading / refetching | A previous preview may still be on screen — **it is not new evidence** |
| Non-empty | Current dry-run candidates, ranked |
| Empty `[]` | **Ambiguous by contract** — no match, or short input, or degraded memory, or a network fault, or a backend memory exception |

**The honesty rule:** every failure returns `[]`, never a 5xx. So an empty preview is
**indistinguishable from a backend fault**, and the UI must not render it as "nothing
in memory matched". Narrowing that needs a new contract — file it in `requests/`.

Three more things the UI must not claim:

- **Preview is not persistence.** It says "in reach", never "saved".
- **`projectId` scopes the wiki tier only.** Learned semantic and episodic tiers in
  Qdrant are still account-wide. Do not claim project isolation for them.
- Learned hits carry synthetic `preview_<n>` ids. **Render-only** — never link,
  update, or delete through one.

Resting `GET /memory` entries are persisted wiki or episodic memory. Episodic writes
exist only from *delivered* runs.

---

## 2. Live LEDGER — incremental, and lossy on purpose

`log` frames arrive as the pipeline emits them (`DecisionLogSink(run.on_log_entry)`
maps synchronously), not as a terminal burst. Animate what arrives.

### What the wire shape drops

The pipeline's internal entry is richer than what ships:

| Field | Internal | On the wire | Consequence |
|---|---|---|---|
| `turn` | present | **dropped** | You cannot group ledger entries by turn. Use `/thread` |
| `detail` | typed `Record<string, unknown>` | **stringified** into `meta` | `meta` is display metadata, **never typed authority**. Do not parse a number back out and compute with it |
| `kind: "message"` | a log kind | **routed to `message_delta`** | Conversational text is not a ledger entry. Never render it as one |

### Kinds

> The **vocabulary** below is introspected from `DecisionLogKind` by
> `sse_contract_drift.py`. If this list and the code disagree, **the code wins and this
> is the bug.** The *render meaning* per kind is not in any test — that part lives here
> and nowhere else.

| Kind | Means |
|---|---|
| `hydration` | Memory/context hydration |
| `route` | Orchestrator routing choice |
| `expert_spawn` | Expert selected — also emits an `expert` frame in `working` |
| `tool_call` | Tool invoked. `meta.tool == "recall"` presents as session recall |
| `observation` | Tool or expert observation |
| `answer` | Outcome/draft landing |
| `warning` | An honest degraded-path notice — **render it, never swallow it** |
| `error` | Pipeline or runtime error |

Expert frames **replace by id** — settlement repeats the id with a new status.
Statuses actually emitted: `working`, `done`, `failed`. The frontend type also admits
`spawned` and `summarizing`, which the backend does not emit — forward-compatible
vocabulary, not a live guarantee. Same for `usage`: the frontend and
`backend/api/README.md` both declare it and **no backend site emits it**. Token usage
comes from persisted REST.

---

## 3. Live ledger ≠ durable audit — never substitute one for the other

Two different things with confusingly similar names.

| | Live `DecisionLogEntry` | Durable `DecisionRecord` |
|---|---|---|
| Purpose | animate work as it happens | institutional-memory projection, queried after |
| Source | SSE `log` frames | `GET /runs/{id}/decisions` |
| Covers | all kinds | **only `tool_call` and `answer`** |
| Carries `turn` | no | yes |
| Guaranteed | yes, if the frame arrived | **no — best-effort mirror write** |

Derivation runs from `finally` for every published terminal status: `delivered`,
`blocked`, `failed` (including on exception), and `cancelled`. Cancellation and
exception paths still preserve the expert/tool participants recorded before the
interruption, because API execution keeps the authoritative pipeline context from
`prepare()`.

**`reasoning` is best-effort and never fabricated** — the nearest preceding `say()`,
otherwise `""`.

**An empty array is not proof that no decision occurred.** It means no derivable
entries, or a pre-CB4 run, or a mirror write that did not land. The UI must not render
"no decisions were made".

---

## 4. Delivery ordering — what to trust, and when

Successful delivery:

1. status / log / expert / message frames
2. `verification`, once the output filter returns
3. `sources`, once — **may be empty**, meaning the run ran no grounded search
4. `report_delta` chunks
5. `report_done`
6. terminal `status: "delivered"`
7. `message_done`, sentinel, synchronous persistence, then the client-observable clean
   close

`report_done` strictly precedes `status: delivered` — pinned by
`tests/sse_terminal_order.py`.

**After the clean close, refetch `GET /runs/{id}`.** That is the authority. Runtime
replay exists only while the run is in memory: reconnecting *during* execution replays
the full buffered sequence; reconnecting *after* eviction to SQLite replays **nothing**
and simply closes. A client revisiting a past run fetches it, and must never wait on
the stream to re-deliver content.

Block paths:

| Blocked at | `verification` emitted? | Why |
|---|---|---|
| output filter | **yes**, then `status: blocked` | the filter ran |
| sanitize / verify | **no** | the filter never ran, so there is no verdict |
| `failed` / `cancelled` | usually no | same reason |

---

## 5. The VERIFIED seal — earned, or absent

Lineage:

```
security/filter/schemas.py  FilterResult.groundedness
  → run_driver: run.on_verification(...)
    → RunState.verification_state
      → SSE {"type":"verification","state":...}
      → run_store.verification_state column
        → GET /runs/{id} "verificationState"
```

**`proceed` and groundedness are independent.** A safe but partial draft can proceed;
blocked output can still carry a verdict. Never infer one from the other.

> Same rule: the **state vocabulary** is checked against the frontend fixture; the
> **treatment** column is not, and is the reason this table exists.

| Persisted state | Meaning | Treatment |
|---|---|---|
| `grounded` | claims grounded in checked sources | positive VERIFIED |
| `partial` | some support, not fully grounded | qualified — **never plain VERIFIED** |
| `ungrounded` | checkable claims lack grounding | warning, or no seal |
| `not_applicable` | no checkable claim to ground | neutral — **never VERIFIED** |
| `null` / absent | the filter never ran, or a legacy run | **no verification claim at all** |

**Eligibility uses persisted `verificationState`, after the clean close and refetch.**
`reportDone`, `status: delivered`, and filter `proceed == true` **never** earn a seal
on their own. The SSE verdict may prepare an animation; it must not become durable
truth until REST confirms it.

That is the difference between a seal that means something and a decoration that says
"the report finished."

---

## 6. Filing a change

Any accepted change to a shared shape moves **all of these together**, or it is drift:

`backend/api/README.md` · frontend types + client · the C6 drift fixture and tests ·
`ROUTES.md` · this file · the `requests/` entry's `## Response`.

---

## 7. Corrections to v1 — verified by reading the code, 2026-08-02

v1 closed with five alignment items and a "current frontend mismatch" section.
**All five are done.** Recorded because a stale "the frontend must still do X" is worse
than no note — it sends someone to redo finished work.

| v1 claim | Reality on 2026-08-02 | Evidence |
|---|---|---|
| live reducer ignores `verification` | **handled** | `frontend/src/lib/api/hooks.ts:408` |
| seal renders from `reportDone` | **uses persisted state after terminal** | `hooks.ts:527` |
| `VerifiedSeal` has no `state` prop | **has one** | `frontend/src/components/brand/verified-seal.tsx:26` |
| ledger and durable records conflated | **kept separate** | §3 still holds |
| hydration caveat unpreserved | **preserved** | §1 |

All five verification states render distinctly
(`frontend/src/components/app/verification-status.tsx`): `not_applicable` → "No
verification needed", `ungrounded` → a destructive "Not grounded" with an explanation,
`grounded`/`partial` → the seal with different copy, anything else → **nothing at
all**. Contract satisfied, not approximated.

**Also dropped from v1:** the SSE event/payload table — it duplicated a
machine-checked source (`ROUTES.md` §2) — and the commit changelog, which git history
already holds and which rots faster than anything else in a contract.
