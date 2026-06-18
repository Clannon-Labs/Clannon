# Premium Feel — research dossier & implementation guides

> Goal: make Clannon look and feel **premium enough to justify $29 / $79 / $199 tiers**.
> Scope: frontend-led, with the minimum backend support that a premium frontend demands.
> Status: research + recommendations. Nothing here is wired yet. Pick from the rollout tiers.

This folder is the output of a deep research pass (7 parallel research streams, June 2026) cross-referenced against the *actual* current frontend. Every recommendation is concrete to this stack — **Next.js 16.2.9, React 19.2, Tailwind v4 (CSS-first / OKLCH), Motion v12, Fraunces / Schibsted Grotesk / Spline Sans Mono** — and links to a primary source.

---

## The thesis (read this first)

Premium is **not** "more effects." For a paid B2B research tool, premium reads as: **fast, intentional, and alive.** Three things, in priority order:

1. **The work feels alive and legible.** Your centerpiece is watching an orchestrator spawn parallel experts, call tools, and stream a report. That moment is the single most convincing "this is expensive software" asset you have — more than any hero gradient. Most of the budget goes here.
2. **Nothing janks.** A laggy tap (INP), a layout shift, a buffered stream, a janky scroll — each one is a pricing objection. Performance *is* the premium signal.
3. **Restrained, considered detail.** Tinted layered shadows, optical-sized type, a tasteful theme-toggle reveal, a completion chime. The small stuff that says "someone cared," applied sparingly. Stripe/Linear/Vercel ship *less* motion than you'd think, not more.

The fastest way to look cheap is to bolt on flashy templated effects (Aceternity 3D card flips, neon shimmer buttons, full-screen Spline scenes). The research repeatedly flags these as the "generic AI landing page" tells. **You already avoid them** — keep avoiding them.

---

## What you already have (don't rebuild these)

The codebase audit found that a large slice of the "premium baseline" is already shipped:

| Already done | Where |
| --- | --- |
| Grain / film texture (SVG `feTurbulence`, ~free) | `globals.css` `.grain` on `<body>` |
| Frosted glass surface | `globals.css` `.glass` |
| "Stage" atmosphere (radial bloom + ember + vignette) | `globals.css` `.stage`, tokens in `theme.config.ts` |
| Premium editorial type trio (Fraunces opsz/SOFT/WONK, Schibsted, Spline Mono) | `layout.tsx` via `next/font` |
| Global reduced-motion honor | `providers.tsx` `<MotionConfig reducedMotion="user">` + CSS media block |
| Theme flash avoidance (pre-paint class) | `public/theme.js`, `beforeInteractive` |
| Skip link, focus-visible rings, `aria-live` on the log, touch targets, safe-area insets | `layout.tsx`, `decision-log.tsx`, `globals.css` |
| A typed SSE event union + mock/http/fold/reconnect | `src/lib/api/{types,mock,http,hooks}.ts` |
| A restrained Motion vocabulary (TypeSet / Stagger / Reveal / Rule, `EASE = [0.16,1,0.3,1]`) | `src/components/motion.tsx` |
| All color centralized in one file (strictly enforced) | `src/config/theme.config.ts` |

This is a strong base. The guides below are about the **delta** from "nicely built" to "premium asf," not a teardown.

---

## How these documents fit together

```
README.md          ← you are here. Strategy, rollout tiers, the map.
CONTRACT.md        ← the give/get between frontend & backend. The SSE event vocabulary.
                     BOTH agents read this. It is the interface.
FRONTEND.md        ← everything client-side. Motion, visuals, type, streaming UX,
                     components, finishing touches, performance. The bulk of the work.
BACKEND.md         ← ONLY the extra data/behavior a premium frontend demands.
                     Additive SSE fields, throttling, anti-buffering. Nothing core.
AGENT_TOOLING.md   ← the tools/skills/plugins/MCP an AI agent uses to BUILD and
                     VERIFY a premium frontend (frontend-design skill, shadcn MCP,
                     Figma MCP, Playwright/Chrome-DevTools loop, etc.).
```

**Reading order by role:**
- Frontend agent → `CONTRACT.md`, then `FRONTEND.md`, then `AGENT_TOOLING.md`.
- Backend agent → `CONTRACT.md`, then `BACKEND.md`. Do **not** read `FRONTEND.md` for implementation; it's out of your lane.
- Root manager / you → this file, then `CONTRACT.md`.

The hard rule the user set: **no frontend implementation detail in `BACKEND.md`, no backend implementation detail in `FRONTEND.md`.** The shared boundary lives in `CONTRACT.md` and only there.

---

## The one decision that unlocks everything: the event contract

Every premium streaming pattern in the research — parallel expert swimlanes, Perplexity-style inline citations, instant skeletons shaped like the real work, the report-reveal moment, live token-budget meters — **degrades to "generic chatbot" if the SSE stream is just text deltas.**

The leverage is in emitting a **typed, ID-correlated event stream.** You already have the bones of one (`RunEvent` in `types.ts`). The recommendation is to **extend it additively** — not rewrite it, not adopt a whole new protocol. The full give/get is in `CONTRACT.md`. This is the highest-ROI item in the entire dossier and the only thing that couples the two teams.

---

## Rollout tiers (pick a tier, not a wishlist)

Ordered by premium-per-effort. **Tier 0 alone moves the whole product up a visible notch and needs zero backend changes.**

### Tier 0 — pure client wins, no backend, low risk (do these first)
- Smooth-stream character buffering on the report (the "ChatGPT feel"). *FRONTEND §4*
- Moss-tinted, OKLCH, layered shadow scale + per-theme shadow tokens. *FRONTEND §2, §6*
- Fluid type scale (Utopia `clamp()` tokens) + tabular-nums on all metrics + `font-optical-sizing`. *FRONTEND §3*
- View-Transitions circular theme-toggle reveal (now Baseline). *FRONTEND §6*
- Block-memoized markdown render to kill streaming reflow jank. *FRONTEND §4*
- Pre-mounted `aria-live` milestone announcer for the decision log. *FRONTEND §6*
- React Compiler on + virtualize the decision log / history rail (INP). *FRONTEND §7*
- Sample-report empty state (aha before token spend). *FRONTEND §6*

### Tier 1 — needs the contract extended (frontend + backend coordinate via CONTRACT.md)
- Parallel-expert **swimlanes** keyed on stable `agentId` (makes your entropy spawn-count *visible*). *FRONTEND §4 + BACKEND*
- Perplexity-style **inline citations** + source hover cards. *FRONTEND §4 + BACKEND*
- **Report-reveal** moment: phase marker → collapse work view → TOC + reading-progress. *FRONTEND §4 + BACKEND*
- Live **token-budget / confidence** meters (surfaces your Lagrangian + entropy math). *FRONTEND §4, §5 + BACKEND*
- Structure-shaped **skeletons** (N expert lanes appear the instant the orchestrator decides N). *FRONTEND §4 + BACKEND*

### Tier 2 — signature polish (do once Tier 0/1 land)
- One lazy, reduced-motion-gated animated hero (Paper Shaders mesh) — *only* the hero. *FRONTEND §2*
- Kinetic editorial headline reveal (hand-split or GSAP SplitText, now free). *FRONTEND §3*
- Restrained UI sound (run-completion chime, default-off) + Android haptic. *FRONTEND §6*
- PPR / Cache Components static editorial shell. *FRONTEND §7*
- Premium pricing page pass (anchoring, usage estimator, trust copy from your security pipeline). *FRONTEND §6*

---

## Hard "avoid" list (from the research)

- **Aceternity 3D card flip / Vortex / 3D Globe, Magic UI Shimmer Button** — the loudest "AI template" tells.
- **Full-screen Spline / heavy R3F** as an ambient background — tanks Core Web Vitals.
- **Cursor-replacement libraries** — mobile-hostile; you're phone-first.
- **`rehype-raw` on LLM output** — re-opens XSS. (Your current `report.tsx` correctly omits it. Keep it that way.)
- **21st.dev Magic MCP generator** — open prompt-injection / supply-chain advisory; skip it. Read-only doc MCPs are fine. *AGENT_TOOLING.*
- **Default `@tailwindcss/typography` `prose` with no overrides**, default glassmorphism everywhere, animated favicons for branding — all read generic.

---

## Source index

Every claim in these docs is sourced inline. The heaviest references, by area:

- **Motion / scroll / transitions:** [Motion docs](https://motion.dev/docs), [Next.js View Transitions](https://nextjs.org/docs/app/guides/view-transitions), [Lenis](https://github.com/darkroomengineering/lenis), [MDN scroll-driven animations](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll-driven_animations), [GSAP now free](https://gsap.com/pricing/).
- **Visuals:** [Paper Shaders](https://shaders.paper.design/), [CSS-Tricks grainy gradients](https://css-tricks.com/grainy-gradients/), [Rauno — Designing Depth](https://rauno.me/craft), [Tailwind v4 shadows](https://tailwindcss.com/docs/box-shadow).
- **Type & components:** [Base UI](https://base-ui.com/), [Streamdown](https://streamdown.ai/), [Vercel AI Elements](https://github.com/vercel/ai-elements), [tweakcn](https://tweakcn.com/), [Utopia fluid type](https://utopia.fyi/).
- **Streaming UX:** [Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), [AG-UI events spec](https://docs.ag-ui.com/concepts/events), [Perplexity citations case study](https://www.aiuxplayground.com/gallery/perplexity-citations/), [Shape of AI — Stream of Thought](https://www.shapeof.ai/patterns/stream-of-thought).
- **Finishing / perf:** [web.dev INP](https://web.dev/articles/inp), [Next.js 16 release](https://nextjs.org/blog/next-16), [React Compiler](https://react.dev/learn/react-compiler/introduction), [The Linear Look](https://frontend.horse/articles/the-linear-look/), [next-themes](https://github.com/pacocoursey/next-themes).
- **Agent tooling:** [frontend-design skill](https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design), [shadcn MCP](https://ui.shadcn.com/docs/mcp), [Figma MCP](https://developers.figma.com/docs/figma-mcp-server/), [Playwright MCP](https://github.com/microsoft/playwright-mcp), [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp).
