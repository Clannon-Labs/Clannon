# Frontend Performance Benchmark

Updated: 2026-07-28  
Environment: Next 16.2.12 production build from `7ff1ca7` plus dirty frontend
worktree, local loopback, Lighthouse 12.8.2, system Google Chrome

## Landing results

Canonical mobile throttling:

| Metric | Baseline | Pass 1 | Pass 2 run A | Pass 2 run B |
|---|---:|---:|---:|---:|
| Lighthouse Performance | 45 | 58 | 63 | 57 |
| Accessibility | — | 100 | 100 | — |
| Best Practices | — | 100 | 100 | — |
| SEO | — | 100 | 100 | — |
| FCP | 2.4s | 2.6s | 1.05s | 1.03s |
| LCP | 6.4s | 4.8s | 3.38s | 4.17s |
| Speed Index | 4.8s | 4.3s | 2.82s | 4.06s |
| Total Blocking Time | 1,620ms | 750ms | 2,298ms | 1,738ms |
| Interactive | 6.5s | 5.0s | 5.07s | 4.91s |
| CLS | 0.003 | 0.002 | 0 | 0 |
| Requests | 50 | 26 | 23 | 23 |
| Transfer | 692 KiB | 450 KiB | 435 KiB | 435 KiB |
| Main-thread work | 7.4s | 4.3s | 7.11s | 6.07s |

Desktop diagnostics, same final build:

| Metric | Run A | Run B |
|---|---:|---:|
| Performance | 95 | 92 |
| FCP | 0.42s | 0.33s |
| LCP | 1.05s | 0.65s |
| TBT | 147ms | 214ms |
| Interactive | 1.11s | 1.00s |
| CLS | 0 | 0.074 |

## Pass 2 changes

- Marketing header, hero ledger, and memory-ring interactions moved from React
  client state to server HTML, CSS, and a tiny root delegation script.
- External `theme.js` request and `beforeInteractive` runtime removed. Inline
  pre-paint theme boot keeps color flash-free.
- Mobile navigation uses native disclosure, supports keyboard activation and
  Escape, closes after anchor navigation, and requires no React hydration.
- Landing retains deliberate motion through compositor-friendly CSS and removes
  state timers from above fold.

## Verdict

Desktop performance now feels premium. Mobile does not meet 90 gate. LCP
improved materially from baseline, request count and transfer fell, and CLS is
stable. CPU-throttled TBT remains volatile and poor because Next App Router
bootstrap plus large document/style work still occupies 1.7–2.3 seconds.

Performance dimension moves 58 -> 64. This is restrained: desktop evidence is
excellent, but mobile performance target is unproven and field Core Web Vitals
remain unavailable.

## Pass 3 (2026-07-28) — honest non-result

Landed two more changes on the same commit line before this pass: theme boot
script inlined (dropped the `beforeInteractive /theme.js` request), and
`Providers` (react-query/motion/toast) scoped out of the root layout into only
`(auth)`/`app` layouts instead of wrapping every marketing page. Re-ran the
same mobile-throttled Lighthouse methodology, three times, against a clean
rebuild (killed and restarted `next start` between builds after one run was
contaminated by a stale-chunk 404 from rebuilding without restarting — not a
real bug, see `reports/frontend/frontend_report_v9.md`):

| Metric | Pass 2 | Pass 3 (3 runs) |
|---|---:|---:|
| Performance score | 63 / 57 | 55 / 59 / 56 |
| TBT | 2,298ms / 1,738ms | 1,590ms / 1,270ms / 1,790ms |
| Main-thread work | 7.11s / 6.07s | 5.2s / 4.5s / 6.0s |
| LCP | 3.38s / 4.17s | 4.7s / 4.3s / 4.3s |

Traced the dominant cost with the `bootup-time` audit: one script chunk at
~1.3–1.6s of scripting time. Verified by string search it contains neither
`react-query` nor `motion/react` — it's Next.js's own Turbopack/RSC-hydration
runtime, 41% unused on this route per `unused-javascript` (framework code for
routes/features this page doesn't touch). Confirmed every marketing component
is already a server component (no `"use client"` in `header.tsx`, `hero.tsx`,
`pipeline.tsx`, `memory-section.tsx`, `pricing.tsx`, `hero-demo.tsx`) — there
is no more app-level JS left to strip from the landing route. The remaining
floor is App Router's own framework overhead.

**Performance dimension stays 64.** Main-thread work looks lower on average;
top-line score and TBT are noisy and land in the same band as Pass 2,
sometimes worse. Not clearing the bar to honestly claim higher, not showing a
regression either. Cutting it further would mean attacking framework-level
behavior (ejecting App Router features, hand-rolling hydration boundaries) —
a real proposal for a dedicated session, not a same-session addition on top of
an unrelated feature ship.

## Command

```bash
NEXT_PUBLIC_API_MODE=mock npm run build
npm run start -- -H 127.0.0.1 -p 3100

npx --yes lighthouse@12.8.2 http://127.0.0.1:3100 \
  --only-categories=performance,accessibility,best-practices,seo \
  --chrome-path=/usr/bin/google-chrome \
  --chrome-flags='--headless=new --no-sandbox --disable-extensions' \
  --output=json
```
