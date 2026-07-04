# CRITIQUE PASS 3 — bar 9 (2026-07-04)

Fresh 36-shot sweep of main @ 42ecb9b (`previews/sweep-pass3-baseline/`),
graded by four independent judges: design lead ("would I sign this?"),
5-second skeptic (AI-default gravity), typography/spacing obsessive, and a
theme-identity director (keep / evolve / replace).

**Pass rate at bar 9: 1 of 36** (run-delivered-L). Set average ≈ 8.3-8.8
depending on judge. Not slop anywhere — but "good is failure."

## THEME VERDICT — unanimous: EVOLVE. Full replacement rejected.

All four judges, independently: the identity (Botanical Archive, moss=verified,
amber=memory, ledger grammar, ring metaphor, Fraunces/Schibsted/Spline) escapes
the AI-default looks exactly at the moments that matter (live ledger, rings,
verified chrome, the copy). Replacement "trades a distinctive, already-shipped
semantic system for a different flavor of distinctive, at full rewiring cost —
when the concept is top-decile and the gap is in surface values, replacement is
vandalism." Fonts: all three stay, all roles stay.

The skin's failures are VALUE-level, and they are specific:

1. **Dark elevation ladder unspent** (workspace-dark = weakest class, 7.5).
   Sidebar/canvas/cards/composer within ~1 L* of each other. Evolution:
   - `background` deepens toward #090d0a (keep green cast, go WARMER-black)
   - `surface-raised` lifts +5-6 L* so the 3 steps span ~3× current range
   - NEW 4th step `stage` (deeper than background) behind hero moments
     (welcome, delivered report)
   - dark gets real shadows (report card, composer) + 1px top edge-light
     hairline on raised surfaces (instrument-panel cue)
2. **Light background one step too close to surface.** Cards read as outlines.
   `background` #f3efe4 → ~#eee9da region (KEEP temperature — warmth is the
   archive); `border-strong` darker so the two border tiers differ.
3. **Amber discipline leaks** — amber is contractually memory-only, but wears:
   auth demo-mode notice (login/signup), SYSTEM MANAGED pill (settings-models).
   De-amber both (neutral surface+border + mono DEMO tag). And amber is OWED
   where it's absent: the memory page renders nearly monochrome.
4. **Dark log spectrum needs +chroma one notch** (violet/cyan near legibility
   floor at 11px on ink) — it's the strongest anti-default signal we have.
5. **THE ONE MOVE** (theme judge): in dark, the verified report lands as a
   LIT SHEET on a dark desk — own surface (~+7 L* over canvas, warm paper-cast
   tint), shadow-lg, hairline top edge-light, stage field behind it one step
   darker. The climax becomes the physical metaphor the brand promises.

## THE SYSTEMIC FAILURE — the energy curve is inverted

The product spends its visual budget before and after work, and almost nothing
on WORK ITSELF. The marketing page literally out-designs the app at the app's
own peak: `demo-mid-L` (6.5/5.5) is routing — a signature moment — rendered as
one 13px caption above ~380px of empty cream. `run-streaming-collapsed-L`
(6.5/6) is the most trust-critical second with the least design in the product.
Fix the run-in-progress canvas and half the table drags upward with it.

## REBUILD LIST (converged, ranked by lift)

R1. **Live-run canvas: reserve the ledger's geometry from second zero.**
    Streaming/collapsed state renders the Decision-log card immediately as a
    skeleton (masthead, rule, spine, ghost rows) that real entries ink into;
    the status verb becomes the card's MASTHEAD, not a caption in a void.
    Same treatment in the demo. Kills demo-mid + streaming-collapsed +
    home-typing dead air in one move.
R2. **Truncation contract, enforced by ONE utility (§11.3).** Word-boundary
    clamps everywhere; never `…` inside a figure (`1.9k…`), never `….`, no
    space before `…`; ONE ellipsis glyph (U+2026) product-wide including
    placeholders. Sites: sidebar recents, landing log lines, wiki clamp,
    drawer, delivered-390 masthead, all placeholders (`...` → `…`).
R3. **Z-axis contract, enforced by ONE primitive (§11.4).** Mask-fade + scroll
    padding wherever a scroll viewport meets a floating layer/clip: palette
    last row, picker footer caption, delivered-fresh ledger (BOTH edges),
    demo-idle-390 ANSWER row, home-rest EPISODIC row + 390 heading, memory-390
    tab rail.
R4. **Report measure 70ch.** Prose runs ~85ch on the payoff screen. One-line.
R5. **Ledger grammar unification.** App masthead gets the marketing card's
    truth: live pulse + run id; entry count must be honest; ONE time register
    (wall-clock in margins; elapsed only in the collapse toggle); ONE spine
    dot size (color carries kind, never size).
R6. **Memory page = the archive, finally.** The empty right half gets the
    tier rings as REAL information design: concentric amber rings w/ live
    counts (Wiki 2 · Semantic 2 · Episodic 1 · Procedural 1), tabs carry tier
    identity. Memory is the brand; its page is the least branded surface.
R7. **Payoff intensified.** Dark lit-sheet (theme item 5); demo: starter-chip
    row DROPS the moment a report exists (chips currently overlap the
    artifact); drop-cap foot on baseline at 390; masthead never wraps
    (mobile label `REPORT`).
R8. **Landing log card honesty.** Top-pin/height-fit entries (45% dead air
    now), word-boundary clamps on log lines, de-glow the italic accent word
    (the "glowing green italic serif" is the most-cloned AI move this year —
    keep the emphasis word, kill the bloom).
R9. **Utility surfaces get the identity.** Palette: runs/memory actions with
    tier dots, fix bottom shear, one hint register. Picker: `GPT-5.5` hyphen
    casing, footer clamp, equal group-header rhythm. Usage chart: zero = flat
    baseline tick ≠ stub, value labels in `.figure`, a mid gridline.
    Settings-models: de-triplicate rows (one icon per role, drop redundant
    "Recommended:" when selected). Billing: `$0/mo` → `Free`; tabular
    fractions.
R10. **Micro-ledger** (typography judge, ~70 items) — full list preserved
    below; each is one-line: eyebrow dot alignment, pricing line balance,
    middot spacing asymmetries, hyphenated-compound breaks, `Privacy Policy`
    link nowrap, form meter snaps, chevron/spine alignments, footer baselines,
    starter-card `text-wrap: balance`, demo `312k tokens` in `.figure`, etc.

## MICRO-LEDGER (fix checklist, from the typography judge)

- landing: log line clamps (`1.9k…`, `regulato…`, `8 res…`) → word-boundary,
  never sever a count from its noun; log card dead top half; pending row gets
  timestamp gutter; eyebrow dot aligns to first-line cap-height (390); CTA
  stack on the 8-grid (390); pricing closing line `text-wrap: balance`; FAQ
  `+` icons centered on x-height.
- demo: starter-card titles `text-wrap: balance`; WHAT YOU'LL WATCH connector
  strokes reach their dots; chip rail right-edge mask (mid); `0:06 · Show
  work` middot spacing; report measure 70ch (done via R4); `312k tokens` in
  .figure; ANSWER row scroll-padding (390); shorter mobile placeholder.
- home: wiki clamp `(CMO)….` → clamp before period; EPISODIC row resting
  shear; sidebar recents clamps; helper-link icon gaps unified (4px vs 6px);
  390 heading shear under scrim; 390 composer `+` inset; hydration chip
  double separator (`·` + amber dot — keep one).
- run: OBS/ROUTE dot sizes → one size; `finishes...` → `…`; blocked: chevron
  on the callout spine axis (6px drift), BLOCKED said once not twice in 40px;
  delivered: header icon gaps evened (20/20/20 not 24/20/20); fresh: ledger
  top+bottom fades; 390: masthead `REPORT` (never wraps), drop-cap foot on
  baseline, single-line placeholder.
- memory: tab helper orphan ("inferred.") rebreak/measure; counts in .figure;
  card title→body 40px → tighten (vs body→ts 26px); `archive...` → `…`;
  390 tab rail affordance.
- drawer: `skincare …` → no space before `…`; nav row pitch 80px → 56-64.
- settings: account helper `re-/verification` no-break; value-rule extent
  consistent; billing `$0/mo` → Free, tabular `1/4` fractions; models:
  SYSTEM MANAGED de-ambered, disabled Verifier gets real disabled state;
  usage: max-value mono label, stubs seated on the baseline.
- auth: demo notice de-ambered (all three frames) + `DEMO` mono tag; `Email *`
  → `Email*` (2px kern); `Privacy Policy` nowrap (390); signup helper gap
  12→8; forgot: columns share an optical axis.
- palette: bottom mask-fade above kbd footer; `search...` → `…`; hint register
  = one (11px mono).
- picker: footer caption reserve-two-lines-or-drop; `GPT-5.5`/`GPT-5.4 Mini`
  hyphenation; group-header rhythm equalized (18px vs 22px).
- legal: contact link+period kept together; footer three columns re-baselined.
- notfound: block to optical center; decide the primary action.

## EXECUTION ORDER (commits)

C1 docs(pass3): this file.
C2 feat(theme): token evolution — dark ladder + `stage` step + shadows/edge-
   light in dark, light bg step, spectrum chroma, amber discipline recolors.
C3 feat(contracts): truncation utility + ScrollFade primitive + 70ch measure +
   ellipsis unification; sweep every violation site (R2/R3/R4).
C4 feat(live-canvas): skeleton ledger + masthead status + ledger grammar
   unification (R1/R5).
C5 feat(archive): memory page tier-ring information design (R6).
C6 feat(payoff): lit-sheet dark artifact + demo chip drop + landing log card +
   de-glow (R7/R8).
C7 fix(craft): utility surfaces + full micro-ledger sweep (R9/R10).
C8 verify: fresh full sweep → previews/, re-grade, report v3.
