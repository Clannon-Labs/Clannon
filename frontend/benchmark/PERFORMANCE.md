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
