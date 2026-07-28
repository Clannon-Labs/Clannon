# Paid Product Benchmark

Status: ACTIVE  
Owner: frontend  
Started: 2026-07-28  
Replaces: screenshot beauty scores as primary frontend benchmark

Current verified score: **83/100**  
Current evidence: `benchmark/PERFORMANCE.md`, `benchmark/FIRST_VALUE.md`,
`benchmark/REAL_JOURNEY.md`, and `reports/frontend/frontend_report_v8.md`

## 1. Question

> If Clannon cost hundreds of dollars per month, would frontend experience make
> purchase feel justified before, during, and after useful work?

This benchmark measures perceived product value. Visual quality matters, but it
cannot compensate for slow loading, unclear value, weak onboarding, avoidable
configuration, fragile recovery, or friction between intent and deliverable.

Backend implementation is outside score. Backend-dependent behavior is judged
through frontend contract and mock states: what user sees, understands, controls,
and can recover from.

## 2. Score

Score is weighted mean of ten dimensions. Each dimension receives 0-100.

| Dimension | Weight | What earns score |
|---|---:|---|
| Outcome clarity | 15 | User understands product, result, limits, and next action without decoding system |
| Time to first value | 12 | Signup to credible deliverable is short, guided, and low-risk |
| Core workflow | 18 | Brief, context, run, review, refinement, export, and reuse form one coherent loop |
| Trust and control | 12 | Sources, memory, spend, models, privacy, status, cancellation, and verification are understandable and controllable |
| Continuity and retention | 10 | Returning work becomes easier; projects, sessions, memory, search, and follow-ups preserve context |
| Performance and smoothness | 12 | Fast first render, low blocking time, stable layout, responsive interaction, restrained motion |
| Failure recovery | 7 | Errors explain impact, preserve work, and offer concrete recovery without dead ends |
| Accessibility | 5 | Keyboard, screen reader, contrast, reduced motion, touch, focus, and semantics work |
| Mobile completeness | 5 | Core paid workflow remains usable and legible on phone, not merely responsive |
| Visual and interaction craft | 4 | Identity, hierarchy, typography, spacing, motion, and detail support comprehension |

### Interpretation

| Score | Verdict |
|---:|---|
| 0-49 | Prototype. Payment would feel premature. |
| 50-69 | Useful beta. Low-price tolerance only. |
| 70-79 | Credible product. Value can justify purchase, but premium price creates doubt. |
| 80-89 | Strong paid product. Most friction is polish or edge-case work. |
| 90-95 | Premium. Hundreds-per-month price feels coherent with experience. |
| 96-100 | Reference-grade. Fast, obvious, trustworthy, resilient, and unusually well-crafted. |

### Current scorecard

| Dimension | Weight | Score | Weighted |
|---|---:|---:|---:|
| Outcome clarity | 15 | 83 | 12.45 |
| Time to first value | 12 | 78 | 9.36 |
| Core workflow | 18 | 85 | 15.30 |
| Trust and control | 12 | 86 | 10.32 |
| Continuity and retention | 10 | 86 | 8.60 |
| Performance and smoothness | 12 | 64 | 7.68 |
| Failure recovery | 7 | 85 | 5.95 |
| Accessibility | 5 | 95 | 4.75 |
| Mobile completeness | 5 | 88 | 4.40 |
| Visual and interaction craft | 4 | 95 | 3.80 |
| **Total** | **100** |  | **82.61 -> 83** |

Pass 2 changed outcome clarity 82 -> 83, core workflow 82 -> 85,
trust/control 84 -> 86, continuity 80 -> 86, performance 58 -> 64,
failure recovery 78 -> 85, accessibility 94 -> 95, mobile 87 -> 88, and
visual craft 94 -> 95. Time to first value stays 78: real execution exceeded
four minutes and eventually returned a partial timeout result.

## 3. Hard gates

Weighted score alone cannot hide critical failure.

### Gate for 80

- New user can reach first credible result without knowing Clannon architecture.
- Core loop has no visible dead end.
- Mobile supports run creation, monitoring, recovery, follow-up, and export.
- No routine action loses user input silently.
- Production performance measured, not inferred from code.

### Gate for 90

- Mobile Lighthouse target: LCP <= 2.5s, INP <= 200ms, CLS <= 0.1.
- No material console errors on public or authenticated critical paths.
- First-run guidance demonstrates why project memory matters.
- Every live-run state answers: what is happening, why, cost, control, and next step.
- Delivered work supports review, source inspection, correction, refinement, sharing, and export.
- Paid-plan differences are visible in workflow value, not only token counts and settings.
- Full browser E2E suite covers critical happy and failure paths.

### Gate for 95

- Repeated use is faster than first use through templates, saved workflows, or equivalent leverage.
- Perceived latency stays useful through progress, partial results, and background continuity.
- Empty, loading, offline, reconnecting, permission, quota, blocked, failed, and partial-verification states are tested.
- User testing confirms comprehension and confidence; internal scoring alone is insufficient.

### Gate for 100

100 is not “no known bugs.” It requires reference-grade proof:

- Core workflow feels inevitable: no explanation needed, no redundant decision.
- Performance meets targets on representative low-end hardware and real network.
- First-time and expert users both move quickly.
- Trust information is deep when requested and quiet when not.
- Multiple external users willingly pay premium price and prefer workflow over alternatives.

## 4. Evidence protocol

Every score update must include:

1. Production build identifier and environment.
2. Desktop and 390px critical-flow browser run.
3. Lighthouse or equivalent performance trace.
4. Console and network error review.
5. Keyboard and reduced-motion pass.
6. Critical-flow E2E result.
7. Changed dimension scores with evidence.
8. Honest limitations and unverified claims.

Static screenshots can support visual findings. They cannot prove performance,
motion, task completion, recovery, or perceived value.

## 5. Critical flows

1. Landing -> understand value -> inspect proof -> pricing -> signup.
2. Signup -> create/select project -> seed context -> first run.
3. Attach files -> submit brief -> monitor work -> cancel/reconnect if needed.
4. Delivery -> inspect verification/sources -> copy/download/preview -> follow up.
5. Return visit -> find prior conversation -> understand recalled memory -> continue.
6. Correct/delete memory -> see future hydration reflect correction.
7. Reach quota/blocked/failed/partial state -> understand impact -> recover.
8. Change plan/model/theme without losing task context.
9. Complete flows 2-7 at 390px and by keyboard.

## 6. Score change rule

Frontend report owns evidence. This file owns rubric.

- Do not raise score for code that has not been exercised in browser.
- Do not raise performance score from bundle estimates alone.
- Do not award backend capability unless frontend exposes it coherently.
- Do not lower score for unavailable backend implementation when mock contract
  proves frontend state honestly.
- Regression in hard gate caps total score below that gate until fixed.
