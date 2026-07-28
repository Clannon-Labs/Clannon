# Backend ↔ frontend integration contract — v1

Updated: 2026-07-26  
Scope: hydration MOMENT, live LEDGER, delivered REPORT, earned verification seal

This file records current executable contract. Backend owns data, authorization,
persistence, and truth. Frontend owns presentation. `backend/api/README.md`,
frontend types, and code must agree with this file; code observations below win
over stale prose until prose is corrected by its owner.

## Surface reconciliation

| Surface | UI need | API provides now | Gap | Resolution |
|---|---|---|---|---|
| Hydration MOMENT | While user types, show memory Manager would actually place in context; resting view shows persisted memory | `GET /memory/hydration-preview` returns ranked dry-run hits; `GET /memory` returns persisted wiki + delivered episodic writes | Preview `projectId` scopes wiki input only; learned semantic/episodic Qdrant tiers remain account-wide. Preview faults collapse to `[]`, indistinguishable from no match | Render preview as best-effort “in reach,” never persistence proof. Render resting memory from `GET /memory`. Do not claim full project isolation until learned tiers gain project scope |
| Live LEDGER | Animate real orchestration activity incrementally, including memory, routing, experts, tools, outcome, warnings/errors | SSE `log` frames carry mapped `DecisionLogEntry`; `expert_spawn` also emits `expert`; expert settlement emits updates | Backend `message` kind is routed to conversational `message_delta`, not ledger. REST log loses source `turn`; mapped `meta` stringifies all detail. Durable decisions use separate endpoint/schema | Animate only received `log` entries. Treat `meta` as display metadata, never typed authority. Keep live ledger separate from durable decision audit |
| Delivered REPORT | Stream filtered deliverable, sources, terminal state; restore completed run after refresh | SSE sources → report deltas → report done → terminal status; `GET /runs/:id` returns persisted report, sources, artifacts, status | Terminal event precedes persistence internally. Stream sentinel is queued before persistence, but synchronous persistence finishes before SSE consumer can observe clean close. Runtime replay disappears after eviction | Use SSE for animation. After clean close, refetch `GET /runs/:id`; persisted REST result is final authority |
| VERIFIED seal | Show earned output-filter verdict, not “report finished” decoration | `FilterResult.groundedness` → `RunState.verification_state`; SSE `{type:"verification",state}`; REST `verificationState` persisted | Frontend types both fields but reducer discards verification event; `VerifiedSeal` has no state prop and renders whenever `reportDone` | Remove unconditional VERIFIED claim. Refetch terminal run, then render state-specific treatment from persisted `verificationState`; absence means no filter verdict, never verified |

## 1. Hydration MOMENT contract

### Endpoint

`GET /memory/hydration-preview?brief=<text>&projectId=<optional-project-id>`

Authenticated, user-scoped, read-only. Frontend waits 500 ms after draft change
and only requests when trimmed brief has at least 3 characters. Query caching
uses `(projectId, brief)`, retains prior data during refresh, and treats results
fresh for 30 seconds.

Response: JSON array, best-first, maximum 8:

```ts
type HydrationPreviewEntry = {
  id: string;                 // real wiki id; learned hits use preview_<n>
  tier: MemoryTier;
  title: string;
  content: string;
  updatedAt: string | null;
  projectId?: string | null;  // wiki project; learned hits currently null
  score: number;              // clamped 0..1
};
```

Backend calls same `MemoryPort.hydrate` door used by runs with authenticated
`user_id`, real trust + similarity + recency ranking, and project-filtered wiki
pairs. Learned tiers are currently account-scoped. Short input, degraded memory,
or any memory exception returns `[]`, never 5xx. Learned `preview_<n>` ids are
render-only: never link, update, or delete through them.

Rendered meanings:

| State | Meaning |
|---|---|
| Draft empty | Resting recap from persisted `GET /memory`; no preview request |
| Draft has 1–2 non-whitespace chars | Listening locally; no preview request |
| Preview loading/refetching | Previous preview may remain visible; not new persisted evidence |
| Non-empty preview | These are current Manager dry-run candidates, ranked best-first |
| Empty preview | No candidate, short input, degraded memory, network fault, or backend memory fault; UI must not distinguish without new contract |
| Resting `GET /memory` entry | Persisted wiki or episodic memory. Episodic writes exist only from delivered runs |

## 2. Live LEDGER contract

### Transport and timing

`GET /runs/:id/stream` is authenticated SSE. Each frame is `data: <RunEvent
JSON>`. Runtime events are buffered while run remains in memory. Reconnect
during execution replays full buffered sequence. After terminal persistence and
cache eviction, stream has no replay; fetch `GET /runs/:id`.

Executable event set:

| Event | Payload | Timing/meaning |
|---|---|---|
| `status` | `{status: RunStatus}` | Coarse phase transition; terminal status is last delivery-status frame |
| `log` | `{entry: DecisionLogEntry}` | Incremental structured ledger entry |
| `expert` | `{expert: ExpertState}` | Expert spawn/settlement snapshot; replace by id |
| `message_delta` | `{text: string}` | Conversational channel chunk |
| `message_done` | none | Conversational channel closes in `finally`, after terminal status |
| `sources` | `{sources: Source[]}` | Once on delivered path, before report; may be empty |
| `report_delta` | `{text: string}` | Filtered deliverable chunk |
| `report_done` | none | Deliverable complete, before delivered status |
| `verification` | `{state: VerificationState}` | Once when output filter ran, before terminal status |

Frontend also declares `usage {tokensUsed}` and API README lists it, but current
backend has no `usage` emit site. Token usage remains available through persisted
REST. This is forward-compatible frontend vocabulary, not a live guarantee.

`DecisionLogSink(run.on_log_entry)` maps entries synchronously as pipeline emits
them. Thus `log` is incremental, not a terminal burst. Expert settlement frames
can repeat same expert id and replace earlier state.

### Live entry source and wire shape

Core source:

```ts
type DecisionLogEntryCore = {
  kind: "hydration" | "route" | "expert_spawn" | "tool_call" |
        "observation" | "answer" | "warning" | "error" | "message";
  message: string;
  turn: number;               // default 0
  detail: Record<string, unknown>;
};
```

SSE/REST presentation for non-`message` entries:

```ts
type DecisionLogEntry = {
  id: string;                 // generated log_<random>
  ts: string;                 // ISO-8601 UTC mapping time
  kind: Exclude<DecisionLogEntryCore["kind"], "message">;
  title: string;              // core message
  meta?: Record<string,string>; // every detail key/value stringified
};
```

`detail` is declared optional by frontend but real backend mapper does not emit
it. Core `turn` is not carried into live/REST ledger shape. Frontend renders:

| Kind | Render meaning |
|---|---|
| `hydration` | Memory/context hydration activity |
| `route` | Orchestrator routing choice |
| `expert_spawn` | Expert selected; also emits `expert` with `working` state |
| `tool_call` | Tool invocation; `meta.tool=recall` is presented as session recall |
| `observation` | Tool/expert observation |
| `answer` | Outcome/draft landing |
| `warning` | Honest degraded-path warning |
| `error` | Pipeline/runtime error |
| core `message` | Not ledger. Appended to conversational `message_delta` channel |

Expert frames:

```ts
type ExpertState = {
  id: string;
  name: string;
  domain: string;
  status: "working" | "done" | "failed"; // values emitted today
  toolCalls: number;
  summary?: string;           // max 400 chars from settled result
};
```

Frontend type also accepts `spawned` and `summarizing`; backend does not emit
them today.

## 3. Durable decision audit contract

Live `DecisionLogEntry` and durable `DecisionRecord` are related but different:
live entries animate work; durable records are an institutional-memory
projection queried after execution.

`GET /runs/:id/decisions` is authenticated and owner-scoped. Foreign/missing run
returns 404. Records sort oldest first:

```ts
type DecisionRecord = {
  id: string;
  traceId: string;            // run id
  sessionId: string;
  turn: number;
  kind: "tool_call" | "answer";
  decision: string;           // source entry message
  reasoning: string;          // nearest preceding say()/message, else ""
  participants: string[];     // tool key or turn expert/tool cast
  decidedAt: string;          // ISO-8601 UTC
};
```

Only `tool_call` and `answer` derive records. Hydration, route, spawn,
observation, warning, error, and message do not. `reasoning` is best-effort and
never fabricated. Empty array means no derived decisions, pre-CB4 run, or a
best-effort mirror write that did not land.

Mirror derivation runs from `finally` for every published terminal status:
`delivered`, `blocked`, `failed` (including an exception), and `cancelled`
(`backend/api/run_driver.py:379-422`, `backend/api/run_driver.py:461-516`).
Only derivable `tool_call` and `answer` entries produce records, and mirror
writes remain best-effort. Crash/cancellation-derived records can carry
incomplete `participants`: without a returned `Flow`, derivation uses a minimal
context plus the live decision log, which lacks returned-flow expert/tool
context (`backend/api/run_driver.py:493-505`). This remains an open CB4 gap.
Frontend must not interpret an empty array as proof no decision occurred.

## 4. REPORT and streaming contract

Create: `POST /runs` multipart → `{id}`. Restore: `GET /runs/:id` → full `Run`.
Live: `GET /runs/:id/stream`.

Relevant persisted REST shape:

```ts
type RunDelivery = {
  id: string;
  status: RunStatus;
  decisionLog: DecisionLogEntry[];
  experts: ExpertState[];
  message?: string | null;
  report?: string | null;
  sources: Source[];
  artifacts: Artifact[];
  blockStage?: "sanitize" | "verify" | "filter" | "security" | null;
  verificationState?: VerificationState | null;
};
```

Successful delivery order:

1. zero or more status/log/expert/message frames;
2. `verification` after output filter returns;
3. `sources` once, possibly empty;
4. `report_delta` frames in six-word chunks, roughly 20 ms apart;
5. `report_done`;
6. terminal `status: "delivered"`;
7. `message_done`, stream sentinel, synchronous terminal row persistence, then
   client-observable clean close.

Blocked filter path emits `verification` then `status:"blocked"`; no report is
delivered. Earlier sanitize/verify blocks have no verification event/state
because output filter never ran. `failed`/`cancelled` may likewise have none.
After clean SSE close frontend refetches run; REST is persisted authority.

## 5. VERIFIED seal contract

Authoritative lineage:

```text
security/filter/schemas.py
  FilterResult.groundedness
    → run_driver: run.on_verification(ctx.filter_result.groundedness)
      → RunState.verification_state
        → SSE {"type":"verification","state":...}
        → run_store.verification_state column
          → GET /runs/:id "verificationState"
```

`proceed` and groundedness are independent: a safe, partial draft can proceed.
Blocked output can still carry a groundedness verdict. Render meanings:

| Persisted state | Meaning | VERIFIED treatment |
|---|---|---|
| `grounded` | Output filter found claims grounded by checked sources | May render positive VERIFIED seal |
| `partial` | Some support exists, but result is not fully grounded | Render qualified/partial state; never label simply VERIFIED |
| `ungrounded` | Checkable claims lack adequate grounding | Render ungrounded warning or no seal |
| `not_applicable` | Turn made no checkable/research claim requiring grounding | Render neutral “not applicable”; never VERIFIED |
| `null`/absent | Output filter never ran, or legacy run predates field | Render no verification claim |

Seal eligibility uses persisted `GET /runs/:id.verificationState`, after clean
stream close/refetch. `reportDone`, `status:"delivered"`, or output-filter
`proceed=True` alone never earns VERIFIED. SSE verdict may prepare animation but
must not become durable seal truth until REST confirms it.

Current frontend mismatch: `Run` and `RunEvent` are typed, but live reducer
ignores `verification`; `VerifiedSeal` accepts only `className`; run page and
marketing demo render it from `reportDone`. Frontend alignment remains required.

## 6. CHANGELOG

- `9f9d6a4`: added filter-groundedness lineage, `RunState.verification_state`,
  persisted REST `verificationState`, and verification SSE emission.
- `6c430c1`: documented verification frame and exercised it in C6 drift harness.
- `3b37d41`: updated frontend-contract fixture for typed verification event.
- `55b2a47`: added durable derived `DecisionRecord` table and owner-scoped
  `GET /runs/:id/decisions`.
- `ea0a79d`: added cross-call code workspace persistence. Internal capability;
  no new frontend payload. Existing report/artifact surfaces expose outcomes.
- `efbbfa6`: added code-symbol indexing tier. Internal capability; no new
  frontend payload.

Frontend alignment requested:

1. fold verification event into live state;
2. after terminal close, use persisted REST `verificationState`;
3. replace `reportDone`-driven generic seal with state-specific rendering;
4. keep live ledger and durable decision records separate;
5. preserve hydration preview’s best-effort and account-wide learned-tier caveat.

## 7. NO-DRIFT RULES

1. No unilateral shared-contract change. Update this file and send proposal
   before changing endpoint, payload, event, enum, timing, or rendered meaning.
2. Backend owns data shape, identity/authorization, filter truth, and
   persistence. Frontend owns rendering and interaction.
3. Live SSE is animation/transport. Persisted REST is final authority after
   terminal completion.
4. Seal and resting memory surfaces reflect persisted reality, never
   `reportDone`, optimistic state, proposed memory writes, or mock inference.
5. Hydration preview is explicitly a dry-run, not evidence memory was persisted.
6. Live decision ledger and durable decision audit stay separate. Neither may
   silently substitute for the other.
7. Any accepted change updates backend API documentation, frontend types/client,
   C6 drift fixture/tests, this contract, and proposal response together.
