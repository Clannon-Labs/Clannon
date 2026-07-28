# First-Value Benchmark

Updated: 2026-07-28  
Environment: Next 16.2.12 development server, mock API contract, system Google
Chrome, Playwright 1.62.0  
Base commit: `86036109ed0a`; captures and results from uncommitted working tree

## Result

Paid-product benchmark: **76 -> 80/100**.

| Dimension | Before | After | Weighted change |
|---|---:|---:|---:|
| Outcome clarity | 76 | 82 | +0.90 |
| Time to first value | 58 | 78 | +2.40 |
| Core workflow | 79 | 82 | +0.54 |
| Trust and control | 82 | 84 | +0.24 |
| Mobile completeness | 84 | 87 | +0.15 |
| **Total** | **75.50** | **79.73** | **+4.23 -> 80** |

Other dimensions remain unchanged. Performance stays 58: this pass improves
task flow, not measured public-page speed.

## Browser journey

Automated critical flow:

1. Sign up as a new user.
2. Reach a genuinely empty workspace; no seeded client data appears.
3. Enter client/project, decision, constraints, and deliverable.
4. Build an editable, project-scoped brief.
5. Review generated wording and send.
6. See live work, user control, and original decision.
7. Wait through full simulated pipeline.
8. Receive report with completed verification controls and no live Stop state.

Result: **2/2 Playwright tests passed**. Desktop full-delivery case completed in
1.2 minutes. Phone-width first-assignment case completed at 390×844. Console and
page-error collector remained empty for desktop critical flow.

Command:

```bash
npm run test:e2e -- e2e/first-value.spec.ts
```

## Product logic

### Empty means empty

Mock signup previously retained seeded projects, runs, memory, and fabricated
usage. This made onboarding look populated but implied cross-account data
exposure. Signup now clears all four. Returning demo login keeps seeded depth.

### Ask for outcome, not architecture

First assignment asks for project, decision, context, and desired deliverable.
It does not ask users to understand agents, memory tiers, model roles, or prompt
formats. Generated brief stays editable before any work starts. Created project
ID travels with brief immediately, so fast send cannot race project-list refresh
and produce an unscoped run.

### One uninterrupted mobile action

Initial implementation kept sticky composer visible behind onboarding. Preview
inspection showed it bisecting phone form. Composer now appears only after brief
exists; first assignment remains one continuous form.

### Expectations stay truthful

UI promises sourced deliverable, claim checks, editability, and cancellation.
It does not invent duration or spend estimates while backend contract lacks
them.

## 80 gate

- First credible result without architecture knowledge: **PASS in mock browser
  contract**.
- Core loop without visible dead end: **PASS for signup through delivery**.
- Mobile paid workflow support: **PASS from existing mobile sweep plus current
  first-assignment check; full mobile automation remains incomplete**.
- Silent input loss: **PASS for checked flow; project-create failure preserves
  entered answers**.
- Measured production performance: **PASS from `benchmark/PERFORMANCE.md`**.

## Limits

- Real HTTP/SSE end-to-end run remains unverified. Backend proposal
  `2026-07-28_frontend-user-journey-test-run.md` is pending.
- No duration or spend estimate before send.
- Browser suite covers one happy path, not session expiry, reconnect, blocked,
  failed, quota, attachment, export download, or keyboard-only journeys.
- Public landing still measures LCP 4.8s and TBT 750ms.
