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

- **[UI_SPEC.md](UI_SPEC.md)** — the complete UI/UX specification: global shell,
  marketing + demo, onboarding, dashboard, project/session space, the task
  execution view (decision log vs. final report), the second-session hydration
  component, memory surfaces, workspaces, jobs, connections, settings, billing,
  safety/trust surfaces, plus the design language (theme, typography, motion),
  voice & microcopy, and the full page inventory.

## Canonical design

[../SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md): **UI And UX** (the
"serious workspace, not a chatbot shell" stance) and **Platform Delivery**
(web default + email/messaging/notifications, platform-agnostic session state).

## The one screen that matters most

The **second-session moment** (UI_SPEC §7): the Memory Manager's hydration
surfacing proactively, in colleague language, with provenance on demand and
inline correction. The spec calls this component "the product." It is the
visible proof of the memory invariants and the Attention Threshold's Pillar 1.

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
