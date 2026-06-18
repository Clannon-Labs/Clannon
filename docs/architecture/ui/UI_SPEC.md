# Vraksha UI/UX Specification (status + remaining backlog)

> **Purpose:** The product surface, tracked as **what's built** (terse notes) vs
> **what's not yet** (the backlog we build from next). The original full spec is
> in git history if a built item ever needs its detail back.
> **Scope:** Web app, task execution view, second-session hydration, memory
> surfaces, workspaces, billing, marketing/demo, plus theme/typography/motion and
> microcopy.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [README.md](README.md) · [../agents/](../agents/) (decision log) ·
> [../memory/](../memory/) (hydration). Implementation: `frontend/AGENTS.md`.

Design stance (unchanged): serious creative/research workspace, not a chatbot
shell. The user should always feel oriented: visible memory, visible reasoning,
visible limits. Nothing hidden, nothing magical.

---

## Status at a glance

**Built and shipped (mock-backed):** global shell, command palette, budget meter,
the task execution view + its block/cancel/reconnect states, the **second-session
hydration moment** (the one screen that mattered most), the memory browser + a
basic wiki editor, billing meter + tier gating + usage graph, model configuration,
auth (email + Google/GitHub OAuth), 404/500 pages, the marketing landing, pricing,
and the **no-signup chat demo** (`/demo`). The home is a ChatGPT/Claude-style
new-chat screen (a deliberate divergence from the §4 dashboard).

**The remaining backlog, biggest first:**
1. **Projects / multi-tenant client space** (§5) — the structural gap: no
   project/client grouping yet (sessions are flat).
2. **Background Jobs** (§10) and **Platform Connections / MCP** (§11) — whole
   surfaces, both need backend contracts.
3. **Notifications** (§15) — in-app inbox + per-channel delivery.
4. **Richer workspaces** (§9) — document (Tiptap), code (CodeMirror), media
   analysis; research citation map + fact/assumption + deep/concise toggle.
5. **Account/settings depth** (§12) — permissions log, notification prefs, memory
   controls, profile/security/sessions, delete-account.
6. **Report polish** (§6b) — inline citations, fact vs assumption, PDF/docx,
   save-to-wiki.
7. **Marketing + email** — About/Security/Changelog/Docs/Contact pages, email
   templates, the Agency team page (open product decision).

Legend: **✓ Built** (terse) · **◻ Not yet** (detailed — this is the work).

---

## 1. Global Shell

**✓ Built:** collapsible left rail (New chat, Search, Memory, recent history,
account menu), Cmd+K command palette, always-visible token budget meter (warning +
exhausted states), theme toggle, mobile drawer + top bar. Logged-out / free / paid /
budget-exhausted states all render.

**◻ Not yet:**
- **Project/workspace switcher** in the rail (it's conversation-centric today; no
  client/project grouping — see §5).
- **Top-bar breadcrumb** (project + session) and a **notifications bell** (see §15).
- **Background-job running indicator** (see §10).

## 2. Marketing Site + Demo

**✓ Built:** landing (hero shows the second-session moment, pillars, pipeline,
memory, pricing teaser, FAQ, footer, auth-aware CTAs); pricing (4 tiers + memory
unlock table + token budgets); **no-signup demo** at `/demo` — a chat exactly like
the workspace, **preset-only**, running a canned, isolated pipeline (never the
backend, costs nothing), with no-memory framing, a soft "watched N runs" nudge, and
the memory-anchored conversion CTA.

**◻ Not yet:**
- IP **rate-limit error state** for the demo — intentionally dropped (canned runs
  cost nothing). It only returns if we ever allow free-typed demo runs.
- Other marketing pages (see Part 2): About/manifesto, Security, Changelog, Docs
  entry, Contact. (Privacy / Terms / Acceptable-use / Refunds exist.)

## 3. Onboarding

**✓ Built:** auth — sign in, sign up, forgot-password; email + Google/GitHub OAuth
buttons. Memory + wiki empty states.

**◻ Not yet:**
- **First-run flow:** create first project → optional client/project facts that
  seed Wiki memory → optional platform connections → land with a guided first task.
- **Auth edges:** OAuth consent return, email verification (sent + confirmed),
  reset-password screen, magic-link variant if used.
- First-class empty states for project list / jobs / connections (once those exist).

## 4. Dashboard (Default Home)

**✓ Built (diverged, kept):** the home is a new-chat screen — greeting, docked
composer (model picker + attach), starter cards, and the second-session hydration
moment — with history in the sidebar. Chosen over the projects/jobs/deliverables
dashboard; the budget card lives in the rail.

**◻ Not yet (only if we want them):**
- **"What Clannon learned recently"** dismissible digest of recent memory writes
  (the trust surface). The Memory browser covers this for now.
- Recent-deliverables list and active/queued jobs on the home (needs §10).

## 5. Project / Session Space  — **largest remaining gap**

**✓ Built:** sessions (conversations) grouped in the sidebar with per-conversation
delete; a whole conversation shares one session; follow-ups continue it; rollover
is invisible (no "context full, start a new chat").

**◻ Not yet — the Project concept:**
- A **project = a client or body of work**; sessions live inside it; the primary
  CTA is "continue working," not "new session."
- **Per-project scope:** its own Wiki, its own memory scope, its own connected
  sources. This is the multi-tenant client structure the whole product implies;
  everything today is flat (no client grouping).

## 6. Task Execution View

**✓ Built:**
- **6a Decision log** — typed, color-coded entries (hydration/route/expert_spawn/
  tool_call/observation/answer/warning/error), collapsed by default behind a live
  "working" verb, `recall` rendered as consulting shared history, distinct EXPERT
  vs TOOL labelling, plus the Experts panel and Sources panel.
- **6b Final report** — distinguished "Verified" card, streamed; copy + download
  markdown; a separate **message channel** (orchestrator commentary, not the
  deliverable).
- **6c States** — blocked by stage (sanitize / verify / filter, each with honest
  copy), user-cancelled, reconnecting, stream-error.
- **6d Input** — multimodal attach with modality icons + heavy-media note; inline
  artifact preview (markdown / text / image / pdf).

**◻ Not yet:**
- **6b:** inline **citation markers → source panel** mapping; **facts vs
  assumptions vs inferences** visual distinction; export to **PDF/docx**;
  **save-to-wiki**.
- **6c:** timeout / turn-cap **"completed under constraints"** note;
  **routed-to-background** acknowledgment + progress handle (needs §10).
- **6d:** explicit **per-modality sanitization feedback** ("file cleaned and
  accepted" vs "file blocked: reason"); **size-limit** and **rate-limit** input
  error states.

## 7. The Second-Session Moment  — **✓ Built (this was the priority)**

Done: colleague language ("Picking up where we left off"), provenance on demand
("Why do I know this?" → trust/source/confidence/recency), inline correction
("That's outdated" / "Wrong — fix it"), recede-to-chip on typing, and the three
states (rich / sparse / corrected). No remaining work.

## 8. Memory Surfaces

**✓ Built:**
- **8b Memory browser** — tiered tabs (wiki/semantic/episodic/procedural),
  subscription gating (locked tiers show an upgrade state), trust/provenance/
  confidence per item, edit/delete, search across memory.
- **8a Wiki** — markdown entries with create/edit/delete, bulk `.md`/`.txt`
  upload, "agents see this on the next run."

**◻ Not yet:**
- **8a Wiki:** rich editor (**Tiptap**), **file tree**, **conflict indicator**
  (where wiki overrides an inferred memory), **templates** (client brief / style
  guide / project facts / research notes).
- **8b:** **pin/boost**, a richer "wrong — correct it" than delete, and the
  **pending memory-write proposal queue** (review-able post-task writes with undo) —
  a strong trust feature.

## 9. Workspaces

**✓ Built:** research output (report + Sources panel) and inline artifact preview
(markdown / text / image / pdf).

**◻ Not yet:**
- **Research:** citation map, fact/assumption separation, **deep-vs-concise toggle**
  as a task option.
- **Document workspace:** Tiptap doc editing of deliverables, versioning per
  session, save-to-wiki.
- **Code workspace:** CodeMirror viewer/editor, multi-file tree, diff view,
  repo-connection state (via MCP).
- **Media analysis:** per-modality result layouts for image/audio/video.

## 10. Background Jobs  — **◻ Not yet (whole surface, needs backend)**

- Jobs list: queued / running / done / failed, with progress, type, and ETA.
- Per-job detail: the **same live decision-log component** as §6a, partial results.
- Completion → notification + result lands in the same delivery surfaces as sync.

## 11. Platform Connections  — **◻ Not yet (whole surface, needs backend)**

- **Delivery channels:** web (default), email, messaging, notifications —
  connect/disconnect, per-channel prefs ("send finished reports to Telegram").
- Cross-platform continuity as a designed moment in the session timeline
  ("started on web, delivered to messaging").
- **MCP integrations:** connect project tools, per-connection permission scope,
  a clear "MCP data passes the same security gates" note, health states
  (connected / auth expired / error).

## 12. Settings

**✓ Built:** per-layer **model configuration** (capability-aware, default marked,
security layers locked read-only); **Usage** tab; **Billing** tab; **Account** tab.

**◻ Not yet:**
- **Permissions & safety:** tool/expert permission-prompt log (what agents may do
  without asking vs must confirm).
- **Notification preferences** per channel and event type (ties to §15).
- **Memory controls:** export, wipe per tier, per-project memory on/off.
- **Profile/security:** change email/password, **active sessions/devices**,
  **delete account** (with explicit memory-deletion consequence copy), **data
  export**.

## 13. Billing & Budget

**✓ Built:** token budget meter (remaining, reset date, 75% / 90% warnings, hard
exhausted blocking state), per-day usage graph, plan/tier cards, checkout hook
(mock applies the plan change in place).

**◻ Not yet:**
- Real **Stripe checkout** + **invoices/receipts**.
- **Per-task cost breakdown**.
- **Tier-change flows** that spell out exactly what memory tiers unlock/lock.

## 14. Safety & Trust Surfaces

**✓ Built:** consistent block/warn/fail messaging (blocked input by stage,
cancelled, stream errors); decision logs retained per run and reviewable in history.

**◻ Not yet:**
- **Permission prompts modal** — when an expert/tool needs elevated access, a clear
  what / why / scope dialog.

## 15. Notifications  — **◻ Not yet (whole surface)**

In-app inbox + per-channel delivery; event types: job complete, budget threshold,
memory-write proposals, connection errors, delivery confirmations. Ties to §10/§11.

---

## Build order — what's left

The original 7-step mock build order is complete through **task view, hydration,
memory/wiki, billing, and marketing/demo**. What remains is no longer "the mock" —
it's the depth pass: **Projects (§5) → Jobs (§10) → Connections (§11) →
Notifications (§15) → richer Workspaces (§9) → settings/account depth (§12) →
report polish (§6b)**. Jobs, Connections, and Notifications are backend-gated;
coordinate via `conversation/proposal*.md`.

States checklist still applies to every NEW screen: empty, loading, populated,
error, locked (tier-gated), budget-exhausted.

---

# Part 2 — Design Language, Copy, Missing Pages

**✓ Built:** the **"Botanical Archive"** design system is implemented — every color
token in `frontend/src/config/theme.config.ts`, the serif/sans split = decision-log
vs final-report, Lucide icons per decision-log kind, Motion for the hydration
recede / report arrival / log stagger, dark + light modes. Voice and the canonical
microcopy (hydration header, correction copy, budget warnings, block messages, 404,
etc.) are wired into the surfaces that exist. Treat §16–§17 of the prior spec (in
git history) as the standing reference for tone and tokens; they don't need
restating here.

**◻ Not yet — pages & surfaces (the inventory that's still missing):**
- **Marketing:** About/manifesto, Security page (the layered-gates story in human
  language), Changelog, Docs entry point, Contact. (Privacy / Terms /
  Acceptable-use / Refunds and the 404 + 500 pages already exist.)
- **Auth edges:** email verification (sent + confirmed), reset-password screen,
  OAuth consent return, magic-link variant if used.
- **Account:** change email/password, active sessions/devices, delete account
  (memory-deletion consequence copy), data export. (Mirrors §12.)
- **Legal:** subprocessors page (agencies handling client data will ask).
- **Email templates** (design these too): verification, job-complete,
  budget-threshold, invoice/receipt, weekly digest (optional, off by default).
- **Agency tier — open product decision:** the $199 tier implies teams (seats,
  shared projects, shared memory scope). Architecture doesn't define it yet — mock a
  placeholder team-settings page and flag the decision; don't invent the model
  silently.
- **Responsive cut (mostly handled):** dashboard/home, run reading, hydration
  review/correct, and the demo are phone-first today. Wiki editing and the code
  workspace remain desktop-first by design.
