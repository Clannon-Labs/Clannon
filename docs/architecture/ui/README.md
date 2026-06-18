# UI / UX

> **Purpose:** Entry point for the product surface — every screen, state, flow,
> the design language, and the voice.
> **Scope:** Web dashboard, task execution view, the second-session hydration
> moment, memory surfaces, workspaces, billing, marketing, and platform delivery
> UX. Backend contracts the UI consumes live with the relevant subsystems.
> **Authority level:** Tier 5 (Subsystem). Inherits
> [../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) and the Invariants.
> **Related:** [../agents/](../agents/) (decision log) ·
> [../memory/](../memory/) (hydration) · [../../glossary/TERMS.md](../../glossary/TERMS.md)

## Contents

- **[UI_SPEC.md](UI_SPEC.md)** — **status + remaining backlog**: what's already
  built (terse notes) and what's not yet (the work we build from), across the
  global shell, marketing + demo, onboarding, project/session space, the task
  execution view, the second-session hydration component, memory surfaces,
  workspaces, jobs, connections, settings, billing, safety/trust surfaces, and the
  design language. The original full spec lives in git history.

## Canonical design

[../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md): **UI And UX** (the
"serious workspace, not a chatbot shell" stance) and **Platform Delivery**
(web default + email/messaging/notifications, platform-agnostic session state).

## The one screen that matters most — built

The **second-session moment** (UI_SPEC §7) — the Memory Manager's hydration
surfacing proactively, in colleague language, with provenance on demand and
inline correction — is **shipped**. It was the priority and it landed: the
visible proof of the memory invariants and the Attention Threshold's Pillar 1.
UI_SPEC.md now tracks the rest as a backlog; the biggest remaining piece is the
**Project / multi-tenant client space** (§5), then Jobs, Connections, and
Notifications.

## Implementation

- `frontend/` — Next.js 16 + Tailwind v4 + Motion v12, the "Botanical Archive"
  design system. Every color token lives in `frontend/src/config/theme.config.ts`.
- See `frontend/AGENTS.md` and `frontend/BACKEND_INTEGRATION.md` before coding
  the frontend.

## Architectural rule the UI must honor

Core loop logic is UI-agnostic. The frontend (and any platform adapter) connects
to the loop and the decision-log sink and exchanges *data only* — it holds no
reasoning logic. The serif/sans split in the design IS the decision-log
(streamed) vs. final-report (buffered through the output filter) split.
