# BACKEND — what a premium frontend demands from you

> Scope is narrow on purpose. This document covers **only the extra data and stream behavior** the premium
> frontend needs — things that are not required for the pipeline to *work*, but are required for it to *feel*
> premium. None of this is core correctness, security, or product logic. For the exact field/event shapes, see
> `CONTRACT.md` (the shared interface). Do **not** read `FRONTEND.md` for implementation — rendering is out of
> your lane.

**Architectural placement (important):** every addition here is a **projection into the SSE/delivery layer**,
not a change to Flow internals. Flow remains the structured inter-stage transport; the api/delivery adapter
already projects Flow/run state into the `RunEvent` stream (`frontend/src/lib/api/types.ts` defines the wire
shape; your server adapter must match it). All new events are emitted from that projection boundary. The
output-filter and verifier remain the sole content authorities — nothing here touches them.

**Guiding principle: additive, optional, backward-compatible.** The frontend ignores events/fields it doesn't
understand. You can ship these one at a time. Don't repurpose existing fields.

---

## 0. The one infra requirement (do this first, it's free and load-bearing)

The entire "streaming feels alive" premium story dies silently if anything between your process and the browser
**buffers the SSE response.**

- **No proxy buffering.** On your stated hosts (Railway backend, Vercel/edge in front), confirm the streaming
  response is not buffered. For nginx-style proxies set `X-Accel-Buffering: no`; ensure no gzip/proxy buffering
  on `text/event-stream`. Flush after every event.
- **Heartbeat.** Emit a comment line `: keepalive\n\n` every ~15 s so idle streams aren't dropped and the
  frontend can distinguish "idle" from "dead" (it has reconnect-with-backoff logic that benefits from this).
- **Correct headers.** `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`.

This requires zero contract changes and prevents the most expensive failure mode (a buffering proxy turns your
38 s live run into a 38 s spinner then a wall of text — the opposite of premium).

---

## 1. Stable IDs and sequence numbers (foundation — CONTRACT §2.1)

The frontend uses ids as React animation keys; without them, layout animations on the live log/lanes thrash.
You already attach `id` to log entries and experts — extend coverage:

| Add | Where | Powers (frontend) |
| --- | --- | --- |
| `seq: number` (monotonic, per run) | every SSE event | cheap dedup on reconnect instead of full-replay |
| `agentId` | in `log.meta.agentId` for expert-related lines (matches `expert.id`) | ties a log line to its swimlane |
| `toolCallId` | tool-call entries / `toolCalls[]` | correlate `start`→`result`, animation key |
| `sourceId` (`Source.id`) | each source | bind inline `[n]` citation chips |
| `sectionId` | report outline + report deltas | TOC + reading-progress |

Ids must be **stable across the run and across reconnect** (don't regenerate on replay) — that's the whole
point. Use deterministic ids (e.g. derived from run id + agent index + tool index), not random per-emit.

---

## 2. Expert roster / spawn event (CONTRACT §2.2)

You already emit `expert_spawn` decisions and per-expert `expert` events. Add **one event that announces the
planned set up front**, the moment the orchestrator decides how many experts to spawn:

```
plan: { experts: [{ agentId, domain, role }], spawnReason?: { entropy, centroidSpread? } }
```

- Lets the frontend render N lanes/skeletons *instantly* instead of one-at-a-time as experts start.
- `spawnReason.entropy` — you already compute Shannon entropy over expert domain centroids to pick the spawn
  count. **Surface that number.** It becomes a visible differentiator ("3 experts · domain entropy 1.8 bits"),
  not debug output. Emit once per run.

This is the single backend change that most directly makes your **math-first architecture visible** to a paying
user.

---

## 3. Per-agent status updates — throttled (CONTRACT §2.3)

`ExpertState.status` exists. Make it **stream incrementally** as each expert progresses, and enrich it:

- `currentTool?` — the tool the expert is running right now ("searching web")
- `progress?` (0–1) — coarse progress
- `tokensUsed?` / `tokenBudget?` — per-expert budget
- `confidence?` (0–1) — if you have it

**Cadence is a hard contract, not a suggestion:** at most **one status update per agent per 200–500 ms.** Never
per token. Coalesce rapid changes. Flooding the stream with per-token status events causes frontend jank — the
exact thing the premium work is trying to eliminate. Text deltas (`report_delta`, `message_delta`) stream
freely; *structured status/metrics* are throttled. This split keeps the stream cheap.

---

## 4. Tool-call lifecycle (CONTRACT §2.4)

Enrich the existing `toolCalls[]` (or emit explicit lifecycle entries) so the frontend can render
input→output→status cards:

```
{ toolCallId, toolName, agentId, args?, result?, status: "running"|"ok"|"error", error? }
```

`args`/`result` should be already-safe, summarized values — not raw tool internals, and obviously nothing that
violates the sub-agent → orchestrator "brief summaries only" rule or leaks anything the output filter would
block. Keep it lean.

---

## 5. Citations — markers + rich sources (CONTRACT §2.5)

Two halves, both required for real inline citations:

1. **Richer `Source`:** `{ id, url, title, domain?, faviconUrl?, snippet?, retrievedAt? }`. You already stream
   `sources` as structured objects — add the id + display metadata.
2. **Citation markers inside the report text, tied to `sourceId`.** The frontend cannot reconstruct which claim
   came from which source — you must place the markers. Recommended: a **post-synthesis CitationAgent-style
   pass** (the pattern Anthropic uses) that locates exact citation positions and inserts stable inline tokens
   (e.g. `[[cite:src_7]]`) rather than asking the synthesizer to guess inline markers mid-stream. This lands
   markers precisely and keeps the streamed prose clean. Final marker token syntax is agreed in `CONTRACT.md`.

The marker pass runs in synthesis/delivery, before/at report emission — it does not change what the output
filter authorizes; it only annotates already-authorized content.

---

## 6. Phase markers (CONTRACT §2.6)

`RunStatus` is coarse. Emit a finer **phase** signal so the frontend knows *when* to trigger the report-reveal
transition instead of inferring it from "text stopped":

```
phase: "planning" | "researching" | "synthesizing" | "delivering" | "done"
```

One event per transition. This is purely a UI timing signal; it doesn't change run semantics.

---

## 7. Report outline / TOC (CONTRACT §2.7)

Emit the report's section structure **before or early in** the report body:

```
report_outline: { sections: [{ id, title, level }] }
```

Then ensure `report_delta` text carries the matching `sectionId` boundaries (or headings the frontend can slug
deterministically). If your synthesizer plans an outline before writing prose (common), emit that plan. This
powers the sticky TOC, reading-progress, and section-shaped skeletons. If an outline isn't available until the
report is structured, emit it as early as you can — even mid-stream is useful.

---

## 8. Numeric run signals (CONTRACT §2.8)

Surface the math you already compute. Extend the existing `usage` event into a richer `metrics` event:

```
metrics: { tokensUsed, tokenBudget?, memoryBudget?: {wiki, semantic, episodic, procedural}, confidence? }
```

- `memoryBudget` — your Lagrangian allocation across memory tiers, per query. Surfacing it makes the
  memory-aware differentiation tangible.
- Throttle to ~200–500 ms (same cadence rule as §3). These drive live budget/confidence meters.

---

## 9. What is explicitly NOT in scope here

To keep lanes clean:

- **No rendering, animation, markdown, or styling concerns** — those are 100% frontend (`FRONTEND.md`).
- **No changes to the verifier or output filter** — security layers stay locked and server-enforced; this doc
  never asks them to relax. Citation/outline annotation operates on already-authorized content only.
- **No change to Flow's schema between stages** — these are delivery-layer projections. If a number you need to
  surface (entropy, memory budget, confidence) isn't currently carried to the delivery boundary, the only Flow-
  adjacent work is *passing that value through to the projection*, not redesigning Flow.
- **No new auth/session/billing work** — unrelated to premium feel.

---

## 10. Optional: AG-UI as the wire format (a bigger, separate decision)

The research notes your backend stack (PydanticAI) is a first-class adopter of the **[AG-UI protocol](https://docs.ag-ui.com/concepts/events)** — a typed, ID-correlated event taxonomy that is essentially a superset of
everything in §1–§8 (lifecycle, text/reasoning channels, tool lifecycle, state snapshots/deltas, activity
events, custom events). Some frontend AI kits ship ready-made AG-UI runtimes.

**Recommendation: do not adopt AG-UI now.** Your existing custom `RunEvent` union is already built, mock-defined,
folded, and reconnect-aware on the frontend. The additive extensions in §1–§8 deliver every premium feature at
a fraction of the risk. Treat AG-UI only as the reference model to keep your event names/shapes sane, and as the
*alternative* you'd consider if you ever rebuild the transport from scratch. If you do go that route, it's a
coordinated rewrite of `types.ts` + `mock.ts` + `http.ts` + `foldRunEvent` + your server adapter together — out
of scope for a premium-feel pass.

---

## Backend checklist (premium-feel scope only)

- [ ] **Infra:** SSE not buffered by host/proxy; heartbeat every ~15 s; correct streaming headers; flush per event.
- [ ] **IDs:** `seq` on every event; `agentId`/`toolCallId`/`sourceId`/`sectionId` stable across run + reconnect.
- [ ] **`plan`** event with expert roster + `spawnReason.entropy`.
- [ ] **Per-agent status** incremental + `currentTool`/`progress`/`tokens`/`confidence`, throttled ≤ 1 per agent per 200–500 ms.
- [ ] **Tool-call** lifecycle fields (`args`/`result`/`status`/`error`), summarized + safe.
- [ ] **Citations:** rich `Source` metadata + in-text `[[cite:id]]` markers via a post-synthesis pass.
- [ ] **`phase`** transitions.
- [ ] **`report_outline`** emitted early + section ids in report deltas.
- [ ] **`metrics`** event (token + memory budget + confidence), throttled.
- [ ] All emitted from the delivery/api projection layer; mock client updated first as the source of truth (coordinate via `CONTRACT.md`).
