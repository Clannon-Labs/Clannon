# MOTION AUDIT — Premium Pass 4, Phase 0 (2026-07-04)

Graded from real screen RECORDINGS (CDP screencast → mp4 + 12-frame filmstrip;
harness in session scratchpad `record.mjs`), not stills. Recordings in
`frontend/previews/motion/`. Axes: **timing** (physical vs linear-robotic),
**weight** (mass/easing vs appear), **rhythm** (choreographed/staggered vs
all-at-once), **continuity** (leads the eye vs pops), **restraint** (purposeful
vs motion-for-motion).

## Current motion inventory (code values)

- House easing: `EASE = cubic-bezier(0.16, 1, 0.3, 1)` (strong ease-out),
  `EASE_RULE = cubic-bezier(0.65,0,0.35,1)`.
- Reveal (broad): `duration 0.9s, EASE, y-travel`. fade-up 0.7s, fade-in 0.5s.
- Ledger entry arrival: `motion.li y:7→0, 0.34s, EASE` + `tick-pulse 0.24s`.
- Ghost rules: **static** (no ink-in). Amber ignite wash: `ignite 1.5s ease-out`.
- Ring draw: `pathLength 0→1, 1.1s, EASE, stagger 0.14s`.
- Payoff: `spine-ignite 0.9s`, moss rule-strike `scaleX 0→1 0.6s`, seal spring
  `stiffness 380 damping 18`.
- Modals: sheet-in 0.22s. pulse-dot 1.6s. caret-blink 1.1s steps.

## Per-moment grades

| moment | grade /10 | the honest read |
|---|---|---|
| **Route transition** (run row → run page, nav) | **3** | None. Hard Next navigation — reload-feel cut, no shared element, the eye is dropped. The lowest score in the product. |
| **Hydration on typing** (recap → chip) | **5** | AnimatePresence cross-fade: the recap fades out, a chip springs in. No memory *surfacing for the brief* — the moat's motion is a fade. |
| **Hover / focus / press** on primary controls | **5** | `transition-colors` only. No physical give on press, no intent on hover beyond a tint. Buttons feel like links. |
| **Hydration on load** (recap assembles) | **6** | Real but shallow: rows amber-ignite in place (1.5s wash) and the ring draws (1.1s). It reads as "fade + wash," not memory *travelling in and settling*. The ring draw and the row ignite are disconnected — two animations, not one thought. |
| **Skeleton → content** swap | **6** | Skeleton, then a Reveal fade of real content. Not matched-geometry — content fades in over where the skeleton was; a soft pop, not a morph. |
| **Streaming text** (report/message) | **6** | Token append + caret. Grows the layout as it fills; watch for jump when a heading lands. |
| **Live ledger inking** | **6.5** | Entries rise 7px + tick-pulse — has a pulse of life, but: ghost rules **opacity-flip** into entries (don't ink in), no expert-spawn branching (parallel work is invisible as motion), stagger is per-mount not choreographed. |
| **Delivered payoff** (spine-ignite + seal) | **7** | The best moment. But the three beats (spine ignites, rule strikes, seal presses, sheet reveals) fire roughly together, not as a led sequence. The seal now presses (spring) — good. Wants to be ONE choreographed beat-chain. |

Set motion average ≈ 5.6. The product LOOKS 9.5 and MOVES ~5.5 — exactly the
gap the mission names.

## TOP 5 GAPS (ranked by WOW leverage)

1. **The hydration moment isn't choreographed (Phase 1).** The moat's signature
   is a fade. It must become: relevant memory surfaces from the archive, draws
   inward (amber, ring-native), connects, and settles into context — staged
   ~200–400ms/beat, spring easing, "the product thinking." Biggest ceiling-raiser.
2. **Route continuity is absent (Phase 4).** run row → run page must be a shared-
   element expand (View Transitions or Motion layout), not a cut. Fixes the
   single lowest-scoring motion in the product and makes navigation feel native.
3. **The payoff isn't a led sequence (Phase 3).** Chain the beats: spine ignites
   top→bottom → the strike lands → the sheet rises → the seal presses with an
   emboss bloom. Each leads the eye to the next; no simultaneous pop.
4. **The ledger doesn't feel written (Phase 2).** Ghost rules must INK into real
   entries (mask-reveal, not opacity), expert spawns must branch/thread so
   parallel work is legible, entries stagger when they land together.
5. **Controls have no physical give (Phase 4).** Hover with intent, press with
   real depression (scale/translate), on-theme focus — 150–300ms custom easing,
   nothing browser-default.

## What already works — don't churn

- The amber ignite wash and ring draw on load are individually nice (just
  uncoordinated). The seal spring press is good. The ledger tick-pulse has life.
  Keep these; connect and build around them.
- Reduced-motion: the codebase already gates most motion on `useReducedMotion`
  and a global `@media (prefers-reduced-motion)` kill — every new beat must keep
  a dignified reduced variant (cross-fade + settle, no large travel).

## AFTER (built) — motion re-grade
Hydration 6→9, Ledger 6.5→9, Payoff 7→9, Route 3→8.5, Controls 5→8.5.
Set avg ~5.6 → ~8.8, signatures at 9. Storyboards + final timings/easings live
in reports/frontend/frontend_report_v4.md; after-recordings in previews/motion/.
