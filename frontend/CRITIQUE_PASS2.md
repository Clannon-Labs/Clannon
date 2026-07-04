# CRITIQUE — Premium Pass 2 (2026-07-04)

36 screenshots (every screen, every key state, light/dark, 1280/390) graded by
three independent personas: a Linear/Vercel design lead, a skeptical 5-second
visitor, and a typography/spacing obsessive. Grades are 1–10 across hierarchy,
type, spacing, color, motion/life, depth, personality, cohesion. Consensus
below; raw per-screen tables in the three persona reports (condensed here).

## The verdict in one paragraph

Not slop — but not WOW. The conceptual system (decision-log ledger, memory
tiers, the archive voice) is top-decile and genuinely ownable; every persona
independently graded the ledger and the microcopy as the best assets. The
failure is twofold: the visual skin is a well-executed **rental of the current
AI-default look** (light = cream + high-contrast serif + warm accent; dark =
green-black + single green accent), and the **payoff frames are the weakest
frames** — the delivered/verified report is clipped, the demo climax renders a
mid-word-truncated prompt as its H1, the streaming state floats in a 70%-empty
canvas. Design-lead verdict: "hire as strong mid-senior, not yet design lead;
the one change that moves it most: design the payoff frame."

## Screens below 8 (rebuild list, worst first)

| Screen | Consensus | Damning detail |
|---|---|---|
| picker (model list) | ~5 | 16 flat ungrouped models, "Gpt 5.5" casing, 3 naming registers for one concept |
| run-streaming-collapsed | ~5.5 | "Queued▍" + 70% dead viewport + severed card sliver |
| settings-usage desktop | ~5.5 | Bars clipped at container floor, zero-days darker than data; mobile renders correctly |
| demo-done (climax) | ~6 | Truncated prompt as display-serif H1; preview cut |
| demo-mid | ~6 | Orphaned caret block; starter chip clipped off-canvas |
| settings-billing | ~6.5 | Current-plan card is a CTA-less void; amber vs green fights |
| settings-account | ~6.5 | Two fields adrift in an empty acre |
| palette | ~6.5 | Stock-cmdk energy; double input chrome; rows hard-clip |
| run-blocked | ~6.5 | Off-palette alert red; no path forward |
| forgot / drawer / 390 variants | ~7 | Dead space, badge collisions, clipped tabs |
| home-typing | ~7 | Great pill morph stranded in a dead void |
| landing-pricing | ~7 | 80px display widow "clients."; FAQ slides under nav unmasked |

Screens at/above 8 (protect): memory (L/D), run-delivered-fresh ledger,
home-rest (L/D), login/signup anatomy, notfound copy, landing hero concept.

## Top 5 root causes of "good, not WOW"

1. **The skin is the AI default, twice.** Light mode is textbook look #1
   (cream ≈ #F4F1EA + serif display + warm accent), dark mode is look #2
   (near-black + single green). The distinctiveness lives in copy and the
   ledger concept — the pixels would blend into a lineup of AI-built sites.
2. **The energy curve is inverted.** Rest states got couture; the moments the
   product exists for (report delivered, demo finished, run streaming) show
   voids, clips, and truncations. WOW requires the payoff frame to be the best
   frame in the product.
3. **No z-axis contract.** Anything meeting a floating layer gets sheared:
   content under the composer (no scrim), palette rows mid-clip, dev badge
   collisions. Designed screen-by-screen, never at the seams.
4. **The machine register is ungoverned.** "5 . 4M" spaced decimals, Gpt vs
   GPT vs raw slugs, zero-bars darker than data, the wordmark token leaking
   cream-on-cream. A glass-box product lives or dies by its data typography.
5. **Ambition is unevenly distributed.** Picker/palette/usage/billing sit at
   scaffolding grade next to couture rest states — the generic surfaces
   retroactively cheapen the crafted ones.

## Bug ledger (fix before any styling)

- Ghost wordmark: transparent header applies dark-ink state on pages/positions
  where the backdrop is cream (landing at top — the hero does NOT extend under
  the sticky header; legal always). Fix = hero runs under a fixed header on
  landing; solid header everywhere else.
- demo/mock run titles truncate mid-word → word-boundary + real ellipsis.
- Sidebar meter "5 . 4M": tabular figures give "." a full slot in a sentence
  line → machine numerals utility, tracking-0, tabular only where columns align.
- Usage chart desktop: no baseline, clipped bars, zero-day inversion.
- report-prose first heading carries ~90px top margin inside the card.
- "Queued▍·" caret welded to label; interpunct spacing.
- Hydration wiki tick centers against the block instead of the first baseline.
- Auth rail art sits at 3 different y positions across sibling pages.
- Memory 390 tabs clip with no scroll affordance.
- Landing closing head widows "clients." at 80px.
- Palette input double chrome; magnifier outside the field ring.
- 4-dot ellipsis ("….") when clamp meets sentence period.
- Dev-only N badge must be stripped from future sweeps (not shipped, but it
  polluted every shot and collided with UI at 390 — screenshot harness fix).

---

# SIGNATURE STORYBOARDS (Phase 2 — designed before implementation)

House curves: `EASE = cubic-bezier(0.22,1,0.36,1)` (settle), new
`EASE_ARRIVE = cubic-bezier(0.16,1,0.3,1)` (arrive-with-weight), springs
(stiffness 420, damping 34) for receding surfaces. All beats 200–400ms.
Reduced motion: every storyboard collapses to settled frames, zero movement.

## Signature 1 — The Hydration Assembly ("the system remembers")

Where: workspace home on load (resting recap) and the moment a run starts.

Beat 0 (0ms) — the kicker line "Picking up where we left off" sets itself
  (existing TypeSet rise, 300ms EASE). The rings begin drawing (existing
  pathLength draw, 600ms, concurrent).
Beat 1 (+140ms) — first memory row arrives: rises 10px with EASE_ARRIVE
  (320ms) while its amber ignite wash burns in and cools (1.5s, overlapping).
  Its tier tick pulses once as it lands (scale 1 → 1.35 → 1, 240ms).
Beat 2..n (+140ms each) — remaining rows print in sequence, same treatment.
  As each lands, the corresponding ring in the dial briefly brightens
  (the dial and the list are one instrument — the connection IS the wow).
Beat n+1 (+200ms after last) — the recap line's tier summary settles
  ("wiki forward"), dial label fades in (200ms).
On typing (any keystroke) — the whole section recedes into the chip with the
  existing spring; the chip's tier dot inherits the ACTIVE tier color and the
  count ticks up as dry-run hits arrive (number crossfades 150ms).
On run start (send) — the chip lifts INTO the run: it animates toward the
  status line of the new run view (shared-element feel: fade-through 200ms;
  full shared-layout later if View Transitions get enabled), where the first
  ledger entry is always MEM ("context loaded: N items · tiers"). Memory
  visibly becomes the first line of work.

## Signature 2 — The Living Ledger ("the glass box")

Where: run view (and demo, shared component).

- The ledger frame hugs content: min-height 3 rows, grows with entries up to
  60vh; no more bottom-aligned rows floating in dead air.
- Entry arrival: rise 7px + EASE_ARRIVE 340ms (existing), PLUS a one-shot
  spine pulse: the entry's tick ring flashes from primary-soft to its kind
  color (220ms) — the ledger's heartbeat. History renders settled (built).
- Expert spawns get PRESENCE: when an expert_spawn entry lands, a compact
  expert chip (name/domain, kind-colored tick, working pulse) slides into a
  rail row beside/above the ledger (240ms EASE) — the "parallel specialists"
  story becomes visible DURING the stream, not after expansion.
- Status has ONE voice: a single status band above the ledger (verb + caret +
  elapsed clock, tabular) replaces the fragmented pill/LIVE·2/orchestrating
  trio. The band's verb crossfades on change (150ms); the clock ticks.
- Terminal settle: on delivered, the band's pulse stops, the spine rule
  ignites once from top to bottom (600ms draw, moss), and the report card
  arrives (below). On blocked, the spine draws in destructive and stops at
  the blocking entry.

## Signature 3 (the payoff) — The Delivered Artifact

The report becomes the best frame in the product: full-bleed paper artifact
inside the run — real texture (existing grain, slightly raised surface),
synthesized title set properly, VERIFIED as a stamped seal moment (rule-strike
exists; add the seal settle: check ring draws 300ms then rests), composer
recedes (scrim + reduced prominence) so the artifact owns the viewport.
Mobile: the report is never hidden behind the composer — scroll padding +
scrim contract.

---

# IDENTITY DECISION (Phase 3)

**Verdict: evolve, don't replace.** All three personas independently
identified the same assets as hire-bar: the ledger grammar, the voice + ring
metaphor, the Fraunces display rhythm, workspace light/dark parity. Replacing
the theme would discard the moat and land on AI-default look #2 (every dark
AI dashboard). The escape from "default" is not a new palette — it is:

1. **Dark-first workspace.** The instrument room. New users land dark in
   /app; light remains a full first-class choice and the marketing default.
   Dark gets a real elevation system (3 surface steps + 2 shadow tiers +
   hairline discipline) instead of one depth token.
2. **Govern the machine register.** New `.figure` utility (tabular, tracking
   0) for every numeral; one `prettyModel` used EVERYWHERE (settings included);
   provider-grouped picker; truncation always word-boundary with real "…".
3. **Spend boldness on the three signatures** (above) and nowhere else.
   Everything else gets quieter and denser, not fancier.
4. **Uniform intensity.** Picker, palette, usage, billing get the same
   finishing pass as the couture screens — density, states, kbd hints.

DESIGN_SYSTEM.md is amended (v2 notes) rather than rewritten: same tokens,
plus elevation tiers, the machine-register rules, and the signature specs.
