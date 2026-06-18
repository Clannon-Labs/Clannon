# CONTRACT — the frontend ↔ backend give/get

> This is the **interface** between the two teams. It is the only document both agents must agree on.
> It describes the SSE event stream: what the backend **gives**, what the frontend **gets**, and which
> premium feature each field unlocks. Implementation detail for each side lives in `FRONTEND.md` / `BACKEND.md`.

**Principle: extend, don't rewrite.** You already have a typed, ID-correlated SSE union (`RunEvent` in
`frontend/src/lib/api/types.ts`). Every premium streaming feature is achievable by **adding optional events
and fields** to that union. No breaking change. The mock client stays the source of truth.

---

## 1. The current contract (what exists today)

From `frontend/src/lib/api/types.ts` — the `RunEvent` discriminated union the SSE stream emits:

```ts
type RunEvent =
  | { type: "status";        status: RunStatus }
  | { type: "log";           entry: DecisionLogEntry }
  | { type: "expert";        expert: ExpertState }
  | { type: "sources";       sources: Source[] }
  | { type: "message_delta"; text: string }   // orchestrator talking, live
  | { type: "message_done" }
  | { type: "report_delta";  text: string }   // the deliverable
  | { type: "report_done" }
  | { type: "usage";         tokensUsed: number }
```

Supporting shapes (already defined):

```ts
type RunStatus =
  | "queued" | "sanitizing" | "verifying" | "orchestrating"
  | "filtering" | "delivered" | "blocked" | "failed" | "cancelled";

type DecisionKind =
  | "hydration" | "route" | "expert_spawn" | "tool_call"
  | "observation" | "answer" | "warning" | "error";

interface DecisionLogEntry { id: string; ts: number; kind: DecisionKind;
                             title: string; detail?: string; meta?: Record<string, unknown>; }

interface ExpertState { id: string; name: string; domain: string;
                        status: ...; summary?: string; toolCalls: ...; }

interface Source { /* url, title, ... */ }
```

**What this already does well** (keep it):
- Stable `id` on every log entry and expert — these are usable as animation keys today.
- `message_delta` (orchestrator commentary) is already a *separate channel* from `report_delta` (the deliverable). The research calls this out as the correct split — it means reasoning vs final report render in different places. **Already done.**
- `expert` events carry `status` + `toolCalls`, so per-expert state is already streamable.
- `sources` already streams as structured objects, not text.

Wire format (`http.ts`): `data: <one JSON RunEvent>\n\n`, blank-line delimited, tolerant of malformed frames and `[DONE]`.

---

## 2. The proposed contract (additive extensions)

Each item below is **optional and backward-compatible**. The frontend ignores events/fields it doesn't
understand; the backend can ship them incrementally. Group by the premium feature they unlock.

### 2.1 Stable IDs everywhere (foundation — do this first)

| Field | On event | Status | Why |
| --- | --- | --- | --- |
| `runId` | all events (or implied by stream) | mostly exists | correlate across reconnect |
| `seq: number` | **all events** | **new** | monotonically increasing sequence number → frontend dedupes on reconnect instead of full-replay rebuild |
| `agentId` | `expert`, and any `log` entry about an expert | exists as `expert.id`; **add to `log.meta.agentId`** | ties a log line to its swimlane |
| `toolCallId` | tool-call log entries / expert tool calls | **new** (in `meta` or `toolCalls[]`) | animation key + correlate `tool.start`→`tool.result` |
| `sourceId` | each `Source` | **new** (`Source.id`) | bind inline `[n]` citation chips to source cards |
| `sectionId` | report outline + report deltas | **new** | TOC links + reading-progress active-section highlight |

> These are the React animation keys. Without them, Motion v12 layout animations on the live log/lanes
> thrash on every update. **Highest-priority backend change.**

### 2.2 Expert roster / spawn event (unlocks: instant swimlanes + structure-shaped skeletons)

You already emit `expert_spawn` as a `DecisionKind` and `expert` events per expert. Add **one event that
announces the planned set up front**, so the UI can render N lanes/skeletons the instant the orchestrator decides:

```ts
| { type: "plan"; experts: Array<{ agentId: string; domain: string; role: string }>;
                  spawnReason?: { entropy: number; centroidSpread?: number } }
```

- `experts[]` → frontend pre-renders one lane per expert with a pulsing "queued" state.
- `spawnReason` (optional) → surfaces your **entropy-based spawn-count** math as a visible differentiator
  ("3 experts — domain entropy 1.8 bits"). This is a *feature*, not debug info. Throttle to once per run.

### 2.3 Per-agent status updates (unlocks: live swimlanes, status pills, "alive" feel)

`ExpertState.status` already exists. Ensure it is **streamed incrementally** as each expert progresses, and add:

| Field on `ExpertState` | Status | Unlocks |
| --- | --- | --- |
| `currentTool?: string` | new | "Researcher → searching web" pill |
| `progress?: number` (0–1) | new | per-lane progress bar |
| `tokensUsed?` / `tokenBudget?` | new | per-expert budget meter |
| `confidence?: number` (0–1) | new | confidence dot / meter |

**Cadence rule:** emit status updates at most every **200–500 ms per agent**, never per token. Flooding React
with per-token status events causes the jank you're trying to avoid. (See `BACKEND.md` for throttling.)

### 2.4 Tool-call lifecycle (unlocks: collapsible tool cards)

Today tool calls live inside `ExpertState.toolCalls` and as `tool_call` log entries. For premium tool cards
(input args → output → status), emit explicit lifecycle events or enrich the `toolCalls[]` entries with:

```ts
{ toolCallId: string; toolName: string; agentId: string;
  args?: unknown; result?: unknown; status: "running" | "ok" | "error"; error?: string }
```

This is additive to the existing `toolCalls` array shape.

### 2.5 Citations (unlocks: Perplexity-style inline `[n]` + source hover cards)

Two parts — both required for real inline citations:

1. **Richer `Source`:**
   ```ts
   interface Source { id: string; url: string; title: string;
                      domain?: string; faviconUrl?: string; snippet?: string; retrievedAt?: number; }
   ```
2. **Citation markers inside the report text tied to `sourceId`.** The frontend cannot reconstruct the
   claim↔source bond from prose. The backend must place markers, e.g. a stable inline token the renderer maps
   to a chip: `... reduces churn [[cite:src_7]].` (final token syntax to be agreed — see `BACKEND.md` for the
   recommended CitationAgent-style post-pass that places these precisely).

### 2.6 Phase markers (unlocks: the report-reveal moment)

`RunStatus` exists but is coarse. Add a finer **phase** signal so the UI knows *when* to collapse the work
view and reveal the report — instead of inferring it from "text stopped":

```ts
| { type: "phase"; phase: "planning" | "researching" | "synthesizing" | "delivering" | "done" }
```

### 2.7 Report outline / TOC (unlocks: TOC rail, reading progress, progressive section skeletons)

Emit the section structure **before / early in** the report body:

```ts
| { type: "report_outline"; sections: Array<{ id: string; title: string; level: number }> }
```

Then ensure streamed `report_delta` text carries the matching `sectionId` boundaries (or headings with stable
`id`s the frontend can slug deterministically). This powers the sticky TOC, the reading-progress bar, and
section-shaped skeletons that fill in as prose streams.

### 2.8 Numeric run signals (unlocks: live budget / confidence viz)

You already compute Lagrangian memory-budget allocation and entropy routing. Surface the numbers:

```ts
| { type: "metrics"; tokensUsed: number; tokenBudget?: number;
                     memoryBudget?: Record<string, number>; confidence?: number }
```

Extends the existing `usage` event. Throttle to ~200–500 ms. These math-first signals are exactly your
differentiation — but only if the numbers reach the client.

---

## 3. Give/get summary table

| Premium feature (FRONTEND.md §) | Backend GIVES (new) | Frontend GETS / renders | Tier |
| --- | --- | --- | --- |
| Smooth-stream report, block-memo render (§4) | nothing — uses existing `report_delta` | buttery token reveal, no reflow | 0 |
| Reasoning vs report split (§4) | already split (`message_*` vs `report_*`) | collapsible thinking + main report | done |
| Stable animation keys (§4) | `seq`, `agentId`, `toolCallId`, `sourceId`, `sectionId` | non-thrashing layout animations | 1 |
| Expert swimlanes + skeletons (§4) | `plan` event (roster + `spawnReason`) | N lanes appear instantly, entropy shown | 1 |
| Live status pills / progress (§4) | `ExpertState.currentTool/progress/...` throttled | "Researcher → searching" pills | 1 |
| Tool cards (§4) | enriched `toolCalls[]` / lifecycle | collapsible input→output cards | 1 |
| Inline citations + hover cards (§4) | rich `Source` + in-text `[[cite:id]]` markers | `[n]` chips, hover source cards | 1 |
| Report-reveal moment (§4) | `phase` event | collapse work → reveal report | 1 |
| TOC + reading progress (§4) | `report_outline` + section ids | sticky TOC, progress bar | 1 |
| Token-budget / confidence meters (§4,§5) | `metrics` event (throttled) | live budget + confidence viz | 1 |
| Reconnect dedup (§7) | `seq` on all events | cheap dedup vs full replay | 1 |

**Pure-client features that need NOTHING from backend** (so frontend can ship them now): smooth-stream
buffering, block-memoized markdown, Streamdown's incomplete-markdown handling, skeleton/shimmer styling,
hover-card mechanics, reading-progress math, TOC active-highlight (if section ids are in the HTML), the reveal
animation, theme view-transition, sound/haptics, all of §6 finishing touches, all of §7 perf.

---

## 4. Process & versioning

1. **The mock client is the source of truth.** When the contract changes, update in this order:
   `frontend/src/lib/api/mock-data.ts` + `mock.ts` (script the new events) → `types.ts` (the union) →
   `hooks.ts` `foldRunEvent` (reduce them into state) → the components → **then** the backend matches.
   This lets the frontend build and demo the premium UI against the mock *before* the backend ships the data.
2. **Additive only.** New events/fields are optional. Old clients ignore unknown `type`s (the `http.ts`
   reader already tolerates this). Never repurpose an existing field's meaning.
3. **One throttling contract:** status/metrics events ≤ one per agent per 200–500 ms. Text deltas
   (`report_delta`, `message_delta`) stream freely. This split keeps the stream cheap.
4. **Heartbeat:** backend sends a comment line (`: keepalive\n\n`) every ~15 s so proxies don't drop idle
   streams and the frontend's reconnect logic can distinguish "idle" from "dead."

---

## 5. Checklists

**Frontend agent must:**
- [ ] Extend the `RunEvent` union in `types.ts` with the new optional events (`plan`, `phase`, `report_outline`, `metrics`) + new optional fields (`seq`, ids, `currentTool`, etc.).
- [ ] Update `foldRunEvent` to reduce them; keep ignoring unknown types.
- [ ] Script them in the mock so the UI is fully demoable offline.
- [ ] Use `seq` for reconnect dedup; use the ids as animation keys.

**Backend agent must:**
- [ ] Emit the new events from the delivery/api projection layer (not from inside Flow internals).
- [ ] Attach stable ids (`seq`, `agentId`, `toolCallId`, `sourceId`, `sectionId`).
- [ ] Throttle status/metrics per the cadence rule.
- [ ] Place citation markers (CitationAgent-style pass) and emit the outline before report body.
- [ ] Ensure the proxy/host does not buffer SSE; send heartbeats.

See `BACKEND.md` for the backend-side detail, `FRONTEND.md` for the rendering detail.
