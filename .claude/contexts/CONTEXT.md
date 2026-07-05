# CONTEXT.md — Session Anchor for Claude Code

**Read this first. Then read `conversation/report_v1.md` → `report_v4.md` in order.**
This file carries the full decision history and working rules from prior architect
sessions. Treat it as authoritative context, not suggestions.

---

## Who you're working with

- Solo founder (Amrit), architect role. You implement; he guides and approves.
- Prefers short, direct, high-signal responses. No essays, no flattery, no re-explaining
  decided things. Push back honestly when he's wrong.
- Goal: Build with Gemini × XPRIZE — needs Gemini integration + real revenue before
  **Aug 17, 2026**.

## What this project is

- **Clannon** = customer-facing brand; **Vraksha** = internal agent engine.
- Premium **Mission Operating Layer**: memory-native multi-agent platform.
  Pipeline (built): client brief → parallel research → synthesis → filtered report.
- Authoritative architecture: **`docs/ARCHITECTURE.md`** (ambition-led, build-state
  tagged: `[BUILT]` / `[PARTIAL]` / `[PROPOSED]`). Never describe PROPOSED as built.
- Detailed canon: `docs/architecture/**`. Code wins over docs when they conflict —
  except security invariants, where a violating implementation is a bug to fix.

## Locked decisions (do not reopen)

1. Mission-OS canonical; built pipeline = execution substrate. Flow = sole transport.
2. Knowledge web `[PROPOSED]`: **Kuzu** (embedded, Cypher) behind **GraphPort**;
   Qdrant stays as vector entry layer; 4 memory tiers become node labels;
   asserted (user, immutable) / inferred (agent) edge typing — asserted wins.
3. Sandbox target: out-of-process (gVisor/microVM); in-process python_exec = deprecated.
4. Embeddings: local fastembed ONNX nomic-768 `[BUILT]`; hosted-API profile `[PROPOSED]`.
   Ollama is NOT the runtime — never reintroduce it in docs.
5. **Mission Engine** `[PROPOSED]` = durability core: persistent cross-session missions
   as state machines in the graph; success criteria at creation; gated verified
   completion; autonomous-by-default with hard budget-pause + irreversible-action
   approval gates; Scheduler/Waker; orchestrator operates the graph (no separate service).
6. Expert routing: entropy = **advisory signal** to orchestrator, not a math decider.
   `[PROPOSED]` — today spawn count is whatever the model emits.
7. Decision-log durable audit mirror `[PROPOSED]` (live stream is `[BUILT]`).
8. Memory-write timing `[BUILT]`: episodic writes fire post-filter/post-delivery only
   (orchestrator.py::persist_turn_memory; pipeline.py::_persist_turn_memory_if_delivered).
9. **§7.3 RESOLVED → sole-broker**: orchestrator (via Memory Manager) brokers ALL
   memory; experts stateless, never query memory directly.

## Current task: NONE — wake messages now sender-authored 2026-07-04 (report_v12, 2e28081): a proposal's optional one-line `Wake:` header is typed verbatim into the recipient ([auto-wake] <line>), else generic default; newest pending file wins; send-keys -l literal. NOTE: reports/ replaced conversation/ (both gitignored, local). Frontend agent mid-mission — do NOT write proposals/to-frontend/ unless asked.

## Prior: wake system live 2026-07-04 (report_v11, dbe22a4): proposals/to-* inboxes auto-wake the target tmux session (clannon-backend/clannon-frontend, start via scripts/agent-session.sh) through clannon-wake@*.path systemd --user units; pause via systemctl --user stop clannon-wake@{backend,frontend}.path. Lingering enabled.

## Prior: proposal protocol live 2026-07-03 (report_v10, commit 822f0bc): check proposals/to-backend/ + backend/proposals/ at the START of every interaction (root CLAUDE.md §PROPOSAL PROTOCOL); format in proposals/README.md; scripts/proposal-status.sh for the owner. One pending item sits in to-frontend/ (dep-bumps FYI) awaiting the frontend agent.

## Prior: security sweep 2026-07-03 (report_v9): #52 gather guard, #18 user_id rate-limit keying, #17 media-route capability judgment, npm audit 7→0 (vitest 4 / plugin-react 5 / next 16.2.10 + postcss override; supersedes dependabot 82/84). Pushed e66be2b..e32bb42. Suite 786 passed, 0 xfail. Bot token: git works, REST/GraphQL blocked (fine-grained PAT) — issue auto-closes unverified.

## Prior: proposals/ processed 2026-07-03 (report_v8): hydration-preview endpoint shipped (e66be2b), SHIPPED answer in proposals/.

## Prior: bot-PR sweep 2026-07-03 (report_v7): 53 merged, 5 needs-work (74/35/63/37 + dependabot 82/84), #39 closed, 6 issues closed. Loop may still be ALIVE (see report_v7 flags).

## Prior: Option D + evolution landed 2026-07-03 (report_v5, report_v6)

Option D (sole-broker): 4 commits (f10f156/19f7ae9/c677117/eab9419) — hydration
push, pre-spawn brokering, grant removal, doc flip. Evolution (report_v6):
NETWORK experts get no push/no channel (ffa4946), need-context tool-shaped
channel for non-NETWORK experts (17f6a74), docs. Suite 300 passed / 6 env skips.
Env note: backend/.venv rebuilt on this box with uv-managed Python 3.12 (project
target); 6th skip = no local clamd.

## Backlog (not now)

- ~~MEDIUM exfil flag from Option D review~~ **CLOSED 2026-07-03** (report_v6):
  NETWORK-capable experts get no hydration push and no need-context channel.
- Need-context, orchestrator-LLM-review variant: requires ExpertOutput contract
  change (need-context field in the expert's return channel + respawn semantics).
  Proposed in report_v6, awaiting owner call. Per-expert bundle slicing also open.
- Delivered-path memory over-reporting: run.memory_writes mirrors proposals; Manager
  may reject some. Fix = Manager returns what it persisted.
- Stop the autonomous loop (`systemctl --user stop clannon-loop`) — net-negative,
  owner does this manually.
- Then §11 roadmap order: production storage/tenancy → Kuzu web → Mission Engine →
  entropy-advisory → audit mirror.

## Working rules (non-negotiable)

- **Discovery → propose → implement.** Propose-first whenever a change touches
  contracts, state ownership, or security boundaries — or when state availability at a
  change site is ambiguous. Trivial/clean changes: proceed.
- **Stop-and-report** if a fix requires structural change bigger than proposed. Never
  force it.
- Tight diffs. No unrelated refactors. Full suite green before every commit.
- Commit per logical unit. End every task with a changelog report file
  (`conversation/report_vN.md`): files changed (file:line), tests, suite result, commits.
- Build-state honesty everywhere: every claim tagged, `[BUILT]`/`[PARTIAL]` cited to
  file:line. If code and docs disagree, flag it.
- Security invariants: user_id scoping at Memory Manager boundary; mid-execution
  retrieved content re-enters sanitization; rejected drafts never touch memory.
