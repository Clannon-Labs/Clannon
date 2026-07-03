# Clannon Design System — "Botanical Archive"

This is the operational definition of premium for the Clannon frontend. Every
visual decision either follows a rule here or updates this file first. Tokens
live in code (`src/config/theme.config.ts` for color, `src/app/globals.css` for
type/motion/texture utilities); this document is the contract for how they are
used.

Product identity: a **premium Mission Operating Layer** — a serious research
and creation workspace. The register is "quiet instrument, visible craft":
closer to a fine printed ledger and a botanist's archive than to a SaaS
dashboard or a chatbot shell.

---

## 1. What "premium" means here, operationally

Distilled from what actually makes Linear, Vercel, Stripe, Notion, Arc, and
Raycast feel expensive — reduced to rules we enforce:

1. **Restraint.** One accent (moss), one semantic secondary (amber = memory,
   always and only memory), warm neutrals. Nothing else, ever. Color is
   information; decoration is texture (grain, hairlines), not hue.
2. **Consistency beats novelty.** The same element is always the same size,
   the same radius, the same spacing, on every screen. A user should be unable
   to tell which screen was built first.
3. **Density with hierarchy.** Serious tools respect the reader's time:
   compact rows, tabular numerals, small mono labels — but always with a clear
   first-read line. Linear's 13px UI base is the reference: small type is
   premium when hierarchy is flawless.
4. **Purposeful motion.** Motion explains causality (what appeared, where it
   came from) or confirms an action. It never performs. If removing an
   animation loses no information, remove it.
5. **Depth without glass soup.** Depth cues are hairline borders, one soft
   shadow tier, and background steps (`background → surface → surface-raised`).
   Blur/glass is reserved for the two docked layers (composer, header) and the
   stage — never for cards.
6. **Every state is designed.** Loading (skeleton, not spinner), empty (an
   invitation, not a void), error (honest, specific, recoverable), streaming
   (alive, smooth), disabled, focus. An undesigned state is a bug.
7. **The keyboard is a first-class citizen.** Focus rings always visible via
   `:focus-visible`; ⌘K palette; Escape always closes; kbd hints in mono.
8. **Type is the brand.** Fraunces (display, with opsz/SOFT/WONK axes) is the
   voice; Schibsted Grotesk does the work; Spline Sans Mono is the machine
   register (logs, tags, numbers). Three fonts, three jobs, no overlap.

## 2. Type

Faces (loaded in `src/app/layout.tsx` via `next/font`):

| Role | Face | Utility | Use |
|---|---|---|---|
| Display | Fraunces | `.display`, `.display-tight` | Headlines, greetings, section mastheads. WONK on, opsz 144. |
| Display-soft | Fraunces | `.display-soft` | Card/panel mastheads, pull lines. opsz 72, SOFT 60. |
| Text | Schibsted Grotesk | `font-sans` (default) | All running UI text. |
| Machine | Spline Sans Mono | `font-mono`, `.tag-label` | Decision log, tags, timestamps, numbers, kbd. |

Scale (px, use these and only these):

- **Display:** 34/42 (page hero, `2.15rem/2.6rem`), 24 (page titles), 15 (panel mastheads via `.display-soft`).
- **UI text:** `15` body-large (marketing lead, greeting sub), `14` body,
  `13` UI base (buttons, list rows, labels), `12` secondary/meta,
  `11` mono-caps tags (`.tag-label`), `10` margin annotations (timestamps).
- Halves (13.5, 12.5, 11.5, 10.5) are legacy; when touching a line, snap to the
  integer scale unless optical size genuinely demands the half.
- **Report prose:** `.report-prose` — 15px/1.75, 70ch measure, Fraunces heads,
  drop-cap only after delivery (`.report-ornate`).
- Numbers that update live are always `.tabular`.

## 3. Spacing & layout

- Base unit **4px**; components use the 4-grid (`gap-2/2.5/3/4/6`), pages use
  the 8-grid (`mt-6/8/10/12`).
- Content measures: app column `max-w-3xl`; report `70ch`; marketing `max-w-6xl`.
- One inset rhythm per container size: cards `p-4` (compact) or `px-5 py-4`
  (standard); panels `px-4 pt-3.5` masthead + `px-4 py-2` body; page gutters
  `px-4 sm:px-6 lg:px-10`.
- Touch targets ≥ 36px (`min-h-9`) always; 44px (`size-11`) for primary mobile actions.

## 4. Color

All values in `src/config/theme.config.ts` — **never** a raw hex/rgb/oklch in a
component, never a default Tailwind palette color (`blue-500` is a firing
offense). Both themes are first-class; dark is green-cast ink, never slate.

Semantic rules:

- `primary` (moss) = action, verification, life. Buttons, links, focus, the
  live pulse, "verified".
- `memory` (amber) = memory, always and only. Hydration, recall, the MEM log
  kind, the tier rings. If it's amber, it's memory; if it's memory, it's amber.
- `log-*` = the five decision-log kind hues; used only in machine register
  (log lines, expert chips).
- `destructive`/`warning`/`success` = outcomes only, never decoration.
- Text tiers: `foreground` → `muted-foreground` → `faint-foreground`. Three
  tiers, no ad-hoc opacities on text (`text-foreground/60` → use the tier).
- Surfaces step `background → surface → surface-raised`; borders step
  `border → border-strong`. Emphasis via the step, not via shadows.

## 5. Radii, borders, elevation

- Radii tokens only: `xs 4 / sm 6 / md 10 / lg 14 / xl 20`; `rounded-full` for
  pills/dots. Same element class ⇒ same radius everywhere (inputs `md`,
  cards `lg`, sheets/menus `lg`, chips `full`).
- Hairline borders (`border-border`) are the primary depth cue — the ledger
  look. `border-strong` for hover emphasis and rules.
- Shadows: at most two tiers — `shadow-md` for floating layers (menus,
  toasts, docked bars), `shadow-lg` for modal sheets. Cards get **no** shadow;
  they get a border and a surface step.
- `.rule-strong` (2px ink) is the editorial masthead rule; `.hairline-*` for
  ledger lines; `.grain` texture stays global and subliminal.

## 6. Motion

Standards (Motion v12 / CSS):

- **Micro-interactions** (hover, press, toggle): 120–200ms, `ease-out`.
- **Entrances** (panels, list items): 200–350ms, `EASE = cubic-bezier(0.22, 1, 0.36, 1)`
  (the house curve, exported from `src/components/motion.tsx`).
- **Receding/expanding surfaces** (hydration chip, drawers): springs,
  `stiffness ~420, damping ~34` — settles under ~350ms, no bounce past 1.
- **Ambient life** (live dots, caret): slow (≥1.1s), subtle, only while
  something is genuinely live. Ambient motion on a dead surface is a lie.
- **Streaming lists** (decision log): each line enters once (opacity + ≤8px
  rise, ~340ms house curve); the container never reflows existing lines;
  auto-follow pins to bottom with a "jump to live" escape hatch.
- **Never** animate `height: auto` on large containers, never animate layout
  properties on scroll containers, never stagger more than ~120ms total.
- Every animated component respects `useReducedMotion()` / the global
  `prefers-reduced-motion` kill switch in `globals.css`.
- Page-level transitions: none. Screens appear settled; motion belongs to
  elements, not routes.

## 7. Component principles

- **Primitives are hand-built** (`src/components/ui/`) — no shadcn/Radix. Any
  new pattern extends an existing primitive; a third variant of "menu" or
  "dialog" is a smell. Popovers portal to `<body>` and clamp to the viewport.
- **States ship with the component.** A component PR without loading/empty/
  error/disabled/focus states is incomplete. Skeletons mirror the real
  layout's geometry (no layout shift on arrival).
- **Optimistic where reversible** (memory correction, ratings): apply
  instantly, roll back with a toast on failure.
- **Data renders dynamically.** No hard-coded expert lists, model names, or
  plan facts — render what the API sends (the backend roster grows without
  frontend releases).
- **Icons:** lucide only, `size-3.5`/`size-4` in UI, `size-5` in feature spots;
  always `aria-hidden` beside a text label. Never an emoji as an icon.
- **A11y floor:** visible `:focus-visible` ring, correct roles/aria on all
  hand-built widgets, focus trap + restore in dialogs/palette, Escape closes,
  `aria-live="polite"` on streaming regions, WCAG AA contrast in both themes
  (muted text runs dark in light mode deliberately — keep it).

## 8. Voice & copy

The UI speaks as a **capable colleague in an archive** — precise, warm, brief.

- First person where the system acts: "I'll route it", "Here's what I'm
  carrying." Never royal-we, never bot-cutesy.
- The botanical metaphor is seasoning, not sauce: allowed in brand moments
  (empty states, the rings, marketing), forbidden in operational/error copy a
  paying user hits under stress. Errors say what happened, what it means,
  what to do next — in that order, honestly ("Nothing was sent to the models.").
- Labels in machine register are mono small-caps and terse (MEM, ROUTE,
  EXPERT). Sentence case everywhere else; no Title Case Buttons.
- Numbers honest and specific ("292 passed", "4 in reach") — never vague
  hype ("blazing fast", "magic").

## 9. Anti-slop rules (hard)

- No gradients on cards; the stage (hero/CTA atmosphere) is the only gradient
  surface in the product.
- No emoji as design elements. No decorative icons without jobs.
- No default-Tailwind blue (or any raw palette color).
- No cookie-cutter hero (badge-headline-subhead-two-buttons-screenshot). The
  landing leads with the live demo — the product is the hero.
- No fake numbers, fake logos, fake testimonials, unsubstantiated claims.
- No glassmorphism beyond the two docked layers + stage.
- No spinner where a skeleton fits; no skeleton that doesn't match real geometry.
- No lorem-ipsum energy: every string in the UI is written for its exact spot.
- No layout shift: reserve space for async content, `font-display` handled by
  next/font, streaming containers own their scroll.

## 10. Signature moments (where we spend the motion/depth budget)

Deliberately uneven investment — these three moments carry the product's feel:

1. **Hydration** (the moat, staged): memory visibly assembling context before
   work starts — amber, ringed, provenance one tap away, receding to a quiet
   chip the instant work begins.
2. **The live decision log** (trust, streaming): a printed ledger that types
   itself — margin timestamps, spine rule, kind ticks; the answer line "ignites".
3. **Delivery** (the payoff): the report settles in with the drop-cap and the
   verified mark — the one ornament, earned at the end.

Everything else stays quiet so these can speak.
