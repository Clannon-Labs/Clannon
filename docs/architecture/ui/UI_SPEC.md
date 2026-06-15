# Vraksha UI/UX Specification (Mock Website Target)

> **Purpose:** The complete product surface — every page, state, flow, the design
> language, the voice, and the marketing inventory.
> **Scope:** Web app, task execution view, second-session hydration, memory
> surfaces, workspaces, billing, marketing/demo, plus theme/typography/motion and
> microcopy.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [README.md](README.md) · [../agents/](../agents/) (decision log) ·
> [../memory/](../memory/) (hydration). Implementation: `frontend/AGENTS.md`.

---

Everything the final product surface needs, derived from the system architecture.
The mock should cover all of this even where the backend is stubbed — the point
is to lock layouts, states, and flows now.

Design stance: serious creative/research workspace, not a chatbot shell. The
user should always feel oriented — visible memory, visible reasoning, visible
limits. Nothing hidden, nothing magical.

---

## 1. Global Shell

- **Left sidebar (persistent):** project/workspace switcher, then within a
  project: Sessions, Wiki, Memory, Jobs, Connections, Settings.
- **Top bar:** current project + session breadcrumb, token budget meter
  (remaining tokens this billing period, color shifts as it depletes),
  notifications bell, user menu.
- **Command palette (Cmd+K):** jump to project, session, wiki page, memory
  item, job, or start a new task.
- **Global states to design:** logged-out, free tier, paid tiers, budget
  exhausted (blocking banner + upgrade CTA), background job running indicator.

## 2. Marketing Site + Demo

- Landing page: value prop is continuity/memory, not "AI agents." Hero should
  show the second-session moment, not a chat box.
- **No-signup demo:** input box → pre-computed output with light
  personalization. Needs: IP rate-limit error state, "this is a demo" framing,
  conversion CTA at the end of the demo output. Demo must visibly NOT have
  memory ("Sign up to make this persistent").
- Pricing page: 4 tiers (Free / Starter $29 / Pro $79 / Agency $199) with the
  memory-tier unlock table (Episodic always; Wiki at Starter; Semantic +
  Procedural at Pro) and monthly token budgets (~2M / ~6M / ~20M).

## 3. Onboarding

- Auth (email + OAuth).
- First-run flow: create first project → optional client/project facts ("tell
  Vraksha about this client") that seed Wiki memory → optional platform
  connections → land in dashboard with a guided first task.
- Empty states everywhere are first-class designs, not afterthoughts: empty
  project list, empty wiki, empty memory, no jobs, no connections.

## 4. Dashboard (Default Home)

- Recent projects and sessions (resume, never "new chat" framing).
- Active/queued background jobs with progress.
- Recent deliverables (reports, docs, code outputs) with open/export actions.
- "What Vraksha learned recently" — a small, dismissible digest of recent
  memory writes (links into the Memory browser). This is the trust surface.
- Budget summary card.

## 5. Project / Session Space

The core unit. A project = a client or body of work; sessions live inside it
but the UI de-emphasizes session boundaries (continuity promise: rollover and
compaction are invisible — never show "context full, start a new chat").

- Session list within a project, but the primary CTA is "continue working,"
  not "new session."
- Per-project: its own Wiki, its own memory scope, its own connected sources.

## 6. Task Execution View (the main screen)

Two distinct streams, visually separated — this is architectural, not styling:

### 6a. Decision Log (live, streams immediately)
- Structured entries, each typed with an icon/badge:
  `hydration`, `route`, `expert_spawn`, `tool_call`, `observation`,
  `warning`, `error`, `answer`.
- Rendered as a collapsible timeline, not prose. Each entry: kind, short
  label, expandable detail (e.g. which experts spawned and why, which tool was
  called with what permission level, confidence signals).
- Hydration entries are special — see §7 (second-session moment).
- Multi-expert tasks: parallel expert lanes or grouped entries per expert.

### 6b. Final Report (buffered, appears after output filter passes)
- Clearly distinguished from the log (card/panel, "verified" affordance).
- Citation-aware rendering: inline citation markers → source panel with
  metadata (source, recency, authority). Facts vs. assumptions vs. inferences
  visually distinguishable for research outputs.
- Export actions: copy, markdown, PDF/docx, save to Wiki.

### 6c. States to design
- Output filter **blocked** a response: structured failure surfaced to user
  ("response failed citation integrity, retrying with a different expert"),
  retry-in-progress, and safe-partial-response with explanation.
- Verifier blocked input (unsafe / unsupported / injection-flagged): clear,
  non-accusatory block message.
- Timeout / turn-cap forced answer: subtle "completed under constraints" note.
- Task routed to background job: immediate acknowledgment + progress handle
  (see §10).

### 6d. Input area
- Multimodal: text, file drop (PDF, image, audio, video) with per-modality
  upload states and sanitization feedback ("file blocked: dangerous content"
  vs "file cleaned and accepted" — at minimum, accepted/rejected with reason).
- Size-limit and rate-limit error states.

## 7. The Second-Session Moment (highest-priority UX)

When a returning user starts work, the Memory Manager's hydration surfaces
proactively, before the user re-explains anything. Design as a distinct
component at the top of the task view:

- **Colleague language**, not database language: "Picking up the Meridian
  account — last time you finalized the Q2 angle and dropped the survey data.
  Their style guide says no em-dashes." NOT "Retrieved 7 memories (0.83
  relevance)."
- **Provenance on demand:** each surfaced item expands to show where it came
  from (which session/source, when, which tier, confidence).
- **Instantly correctable:** inline edit/delete/"that's outdated" on every
  item; correction takes effect immediately and visibly.
- **Then it recedes:** collapses to a one-line summary chip once work starts.
  It must never nag or dominate the screen.

This component is the product. Prototype it in at least three states: rich
hydration, sparse hydration (early relationship), and corrected-item flow.

## 8. Memory Surfaces

### 8a. Wiki (user-authored, highest trust)
- Markdown editor (Tiptap) with file tree, per project.
- "Agents see this instantly" affordance — edits are live truth.
- Conflict indicator: where wiki overrides an inferred memory, show it.
- Templates: client brief, style guide, project facts, research notes.

### 8b. Memory Browser (Semantic / Episodic / Procedural)
- Tabbed or filtered list per tier, gated by subscription (locked tiers show
  an upgrade state, not an empty state).
- Every item shows the universal fields: **trust, provenance, confidence** —
  plus recency. Confidence as a visual scale, provenance as expandable detail.
- Item actions: edit, delete, pin/boost, "wrong — correct it."
- Search across memory.
- Pending memory-write proposals (post-task, async): a review-able queue is a
  strong trust feature — at minimum show recent writes with undo.

## 9. Workspaces

- **Research workspace:** report view with source panel, citation map,
  fact/assumption separation, deep-vs-concise toggle as a task option.
- **Document workspace:** Tiptap-based doc editing of deliverables, versioning
  per session, save-to-wiki.
- **Code workspace:** CodeMirror 6 viewer/editor, file tree for multi-file
  outputs, diff view for edits, repo-connection state (via MCP).
- **Media analysis:** upload → analysis result view (per-modality result
  layouts for image/audio/video).

## 10. Background Jobs

- Jobs list: queued / running / done / failed, with progress, job type, and
  ETA where known.
- Per-job detail: live decision log (same component as §6a), partial results.
- Completion → notification + result lands in the same delivery surfaces as
  sync responses.

## 11. Platform Connections

- **Delivery channels:** web (default), email, messaging platforms,
  notifications — connect/disconnect, per-channel preferences ("send finished
  reports to Telegram," "notify on job completion only").
- Cross-platform continuity is a designed moment: "started on web, delivered
  to messaging" should be legible in the session timeline.
- **MCP integrations:** connect project tools, per-connection permission
  scope display, and a clear note that MCP data passes the same security
  gates. Connection health states (connected / auth expired / error).

## 12. Settings

- **Model configuration:** per-pipeline-layer model selection, filtered by
  capability (vision/audio/long-context), with "default" clearly marked.
  Capability-mismatch validation states.
- **Permissions & safety:** tool/expert permission prompts log, what agents
  may do without asking vs. must confirm.
- **Notification preferences** per channel and event type.
- **Memory controls:** export, wipe per tier, per-project memory on/off.
- Profile, security, sessions.

## 13. Billing & Budget

- Plan management (Stripe), invoices.
- **Token budget meter:** period usage graph, per-task cost breakdown,
  remaining budget, reset date. Warning thresholds (75% / 90%) and the hard
  exhausted state (calls blocked, clear messaging, upgrade path).
- Tier-change flows including what memory tiers unlock/lock.

## 14. Safety & Trust Surfaces (cross-cutting)

- Block/warn/fail messaging system with consistent visual language:
  blocked input, blocked output, warnings that proceeded, hard pipeline
  failures ("something broke on our side") — each distinct.
- Audit access where relevant: decision logs are retained per session and
  reviewable later.
- Permission prompts: when an expert/tool needs elevated access, a clear
  modal with what/why/scope.

## 15. Notifications

- In-app inbox + per-channel delivery, event types: job complete, budget
  threshold, memory write proposals, connection errors, delivery confirmations.

---

## Build order for the mock

1. Global shell + dashboard
2. Task execution view (decision log + final report, all states in §6c)
3. Second-session hydration component (§7) — three states
4. Wiki editor + memory browser with trust/provenance/confidence
5. Billing meter + tier gating states
6. Jobs, connections, settings
7. Marketing + demo last

States checklist for every screen: empty, loading, populated, error, locked
(tier-gated), budget-exhausted.

---

# PART 2 — Design Language, Copy, and Missing Pages

## 16. Visual Theme

**Direction: "quiet instrument."** A calm, editorial, information-dense
workspace — closer to Linear/Notion/Arc than to ChatGPT. The product's promise
is trust and continuity, so the visuals should feel stable, precise, and
unhurried. No gradients-everywhere AI aesthetic, no sparkle emoji, no purple.

### Color
- **Base:** near-white warm paper (`#FAFAF7`-ish) light mode; deep
  charcoal-green (`#101412`-ish) dark mode. Dark mode is first-class (research
  tool, long sessions).
- **Accent (single):** a deep botanical green (Vraksha = tree; own it).
  Used only for primary actions, active states, and the hydration component.
- **Semantic set:** amber = warning/budget thresholds; red = blocked/failed;
  blue = informational/tool activity; muted violet = memory/provenance.
  Decision-log entry kinds each get a fixed hue from this set so the timeline
  is scannable without reading.
- **Confidence scale:** a single-hue ramp (green, 3 steps), never
  red-to-green — low confidence is "uncertain," not "bad."

### Typography
- **UI + body:** Inter or Geist — neutral, dense-capable.
- **Editorial moments** (final reports, hydration card, marketing): a serif —
  e.g. Newsreader or Source Serif — to signal "this is the deliverable, this
  is the colleague speaking." The serif/sans split IS the decision-log vs
  final-report split made typographic.
- **Code/log:** JetBrains Mono or Geist Mono for tool calls, IDs, provenance.
- **Scale: two registers.** The *product* is compact — 13–14px UI base,
  generous line-height in reports only. The *marketing/editorial surfaces*
  (landing, about, pull quotes, page greetings) run at display scale:
  hero serif up to ~76px, section headings 30–52px, ledes 17–18px.
  Quiet ≠ small — restraint lives in color and ornament, presence lives
  in type size and air. A compact pitch reads timid, not calm.

### Layout & density
- 8px grid, 1200–1440px max content width, sidebar 240px collapsible to icons.
- Workspace screens are dense (tables, timelines); report and hydration
  surfaces get whitespace. Density signals "machine," air signals "colleague."
- **Marketing pages: one idea per viewport.** Section spacing breathes
  (roughly 90–170px, viewport-proportional); each section earns its own
  screen instead of stacking. The dense product frame embedded inside the
  spacious pitch IS the contrast that sells the instrument.
- **Phone: progressive disclosure, not stacking.** On small screens the
  dashboard shows one primary card open; secondary cards collapse to slim
  header rows with a count chip. A phone screen holds 1–2 ideas, never six.
  The hidden sidebar is replaced by a bottom nav, and hover-revealed actions
  must be always-visible on touch.
- Cards with 1px borders + subtle shadow, radius 8–10px (up to 12–16px on
  display-scale marketing panels). No glassmorphism.

### Motion (Framer Motion)
- Decision-log entries: slide-in + fade, 150ms, stagger on burst.
- Hydration card: gentle expand on session start, collapse-to-chip with a
  spring once the user starts typing (the "recede" moment is animated, ~300ms).
- Report arrival: fade-up as one block after filter passes — it should feel
  *placed*, not streamed (it wasn't streamed; honor that).
- Nothing bounces. Nothing pulses except live-job indicators.

### Iconography
- Lucide, 1.5px stroke. Fixed icon per decision-log kind: hydration = sprout,
  route = git-branch, expert_spawn = users, tool_call = wrench,
  observation = eye, warning = triangle-alert, error = octagon-x,
  answer = check-circle.

## 17. Voice & Microcopy

**Voice: a sharp colleague.** First person plural avoided; Vraksha speaks as
"I" in hydration/log contexts, plain neutral voice in system messages. Never
cute, never apologetic-corporate, never "Oops!". Confident about what it
knows, explicit about what it doesn't.

### Canonical microcopy (write these into the mock verbatim, then iterate)
- **Hydration card header:** "Picking up where we left off" → items beneath.
- **Hydration provenance toggle:** "Why do I know this?"
- **Correction action:** "That's outdated" / "Wrong — fix it"
- **Corrected confirmation:** "Got it. I won't bring that up again." (toast,
  3s)
- **Sparse hydration:** "First session on this project — I'll start
  remembering from here."
- **Empty wiki:** "Nothing written yet. Anything you put here outranks
  everything I infer."
- **Memory tier locked:** "Semantic memory is a Pro feature. I'm still
  remembering this session either way." (episodic always works — say so)
- **Verifier block:** "I can't take this input forward — it failed a safety
  check. Nothing was processed." (+ reason category, no lecture)
- **Output filter block + retry:** "My first draft failed citation checks.
  Re-running with stricter sourcing…"
- **Safe partial:** "Here's what I could verify. Two claims didn't pass
  sourcing, so I've left them out — details in the log."
- **Budget 90%:** "About 600K tokens left this period — resets June 30."
- **Budget exhausted:** "You're out of tokens for this period. Work is
  paused, nothing is lost. Resets June 30, or upgrade to continue now."
- **Background handoff:** "This will take a while. I'll keep working — you'll
  get a notification. You can watch the log live or close this tab."
- **Job complete notification:** "Meridian competitive report is ready."
- **Session rollover:** *nothing.* No copy exists for this. Invisible.
- **404:** "This page doesn't exist. Your work does — head back to the
  dashboard."

### Decision-log entry phrasing (structured, terse, present tense)
- "Spawning research + data-analysis experts — query spans both domains"
- "Calling web_search (read-only) — 3 sources on EU pricing rules"
- "Confidence low on the 2024 figure — flagging for the report"

## 18. Marketing Site — Page-by-Page Content

### Landing
- **Hero headline (working options):**
  - "The research workspace that remembers your clients."
  - "Stop re-explaining your clients to your tools."
  - "Your second session is where Vraksha gets good."
- **Hero visual:** an animated mock of the hydration card appearing in a
  returning session — NOT a chat box, NOT a feature grid.
- **Section order:** hero → second-session demo (animated) → "how it
  remembers" (4 tiers, plain language: what you write / facts / history /
  habits) → provenance & correctability ("every memory shows its source; every
  memory is one click from gone") → deliverables (research/docs/code) →
  works-where-you-work (platforms/MCP) → security strip (one line per gate,
  small print confidence) → pricing teaser → CTA.
- **CTA copy:** "Try it without signing up" (demo) / "Start free" (auth).

### Demo page
- Framing line: "This is a canned demo — fast, but it has no memory. The real
  thing remembers." Output footer CTA: "Sign up and it never forgets this."
- Rate-limited state: "Demo limit reached from this network — sign up to keep
  going."

### Pricing
- Tier cards + the memory-unlock table + token budgets. One FAQ block:
  what's a token (plain explanation + "a typical deep report ≈ 150–300K"),
  what happens at zero, can I export memory, can I delete memory.

### Other marketing pages
- About/manifesto (the continuity thesis — short, opinionated), Security page
  (the layered-gates story in human language), Changelog, Docs entry point,
  Privacy, Terms, Contact.

## 19. Missing Pages & Surfaces (complete inventory)

- **Auth:** sign in, sign up, OAuth consent return, forgot/reset password,
  email verification (sent + confirmed), magic-link variant if used.
- **Errors:** 404, 500 ("something broke on our side — your work and memory
  are safe"), maintenance, offline/connection-lost banner with auto-retry.
- **Account:** profile, change email/password, active sessions/devices,
  delete account (with explicit memory-deletion consequence copy), data
  export.
- **Legal:** privacy, terms, subprocessors (you're handling client data —
  agencies will ask).
- **Email templates (design these too):** verification, job-complete,
  budget-threshold, invoice/receipt, weekly digest (optional, off by
  default).
- **Agency tier open question:** $199 tier implies teams — seats, shared
  projects, shared memory scope? Architecture doc doesn't define it. Mock a
  placeholder team-settings page and flag the product decision; don't invent
  the model silently.
- **Responsive:** the dashboard/jobs/notifications must work on mobile (users
  get pinged when jobs finish); full workspaces can be desktop-first. Define
  the mobile cut: dashboard, job status, report reading, hydration
  review/correct — yes. Wiki editing, code workspace — desktop.

## 20. Spec completeness check

With Parts 1+2 the mock has: every page, every state, the theme system,
the voice, verbatim microcopy for the critical moments, and marketing copy
direction. Deliberately NOT specified (decide during the mock, not before):
exact spacing tokens, final font pairing, illustration style, logo. Those
should emerge from building §7 first and theming outward from it.
