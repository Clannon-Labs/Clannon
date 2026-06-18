# FRONTEND — premium feel implementation guide

> Everything in this document is **client-side**. Where a feature needs data from the backend, it points to
> `CONTRACT.md` and never describes backend implementation. Stack: Next.js 16.2.9, React 19.2, Tailwind v4
> (CSS-first / OKLCH), Motion v12, `next/font` (Fraunces / Schibsted Grotesk / Spline Sans Mono).
> Color lives only in `src/config/theme.config.ts`; `globals.css` maps tokens → Tailwind utilities. Keep both
> invariants.

**Section map**
1. Motion & micro-interactions
2. Visual effects & atmosphere
3. Typography & layout
4. Streaming / agent UX (the centerpiece)
5. Headless primitives & components to adopt
6. Finishing touches
7. Performance *as* premium
8. Recommended rollout

A cross-cutting rule from every research stream: **animate `transform` + `opacity` only** (compositor-safe),
never `width/height/top/left/box-shadow`. Wrap all motion in `"use client"`. Everything degrades gracefully
under `prefers-reduced-motion` (you already have `<MotionConfig reducedMotion="user">` globally — keep using
it and add CSS `motion-reduce:` for first-paint-critical motion).

---

## 1. Motion & micro-interactions

You have a deliberately restrained Motion vocabulary in `src/components/motion.tsx` (`TypeSet`, `Stagger`,
`Reveal`, `Rule`, `EASE = [0.16, 1, 0.3, 1]`). That expo-out curve is exactly the "premium" bezier the
research recommends — **keep it as your house curve.** The gaps are: smooth scroll, route/page transitions,
and a couple of micro-interactions.

### Standardize these motion values (paste into a `motion-tokens.ts` or keep in `motion.tsx`)

| Token | Value | Use |
| --- | --- | --- |
| Micro (press/hover/toggle) | 100–150 ms | buttons, switches |
| Standard UI | 200–300 ms ease-out | cards, panels, list items |
| Hero / route | 300–400 ms | view transitions, hero |
| Hard floor / ceiling | 80 ms min, 500 ms max | everywhere |
| House bezier (entrances) | `[0.16, 1, 0.3, 1]` | already your `EASE` |
| UI spring | `{ type:"spring", visualDuration:0.4, bounce:0.15–0.25 }` | pop-ins (low bounce = editorial) |
| Drag-release spring | `{ stiffness:300–400, damping:30–40, mass:1 }` | gestures |
| Stagger step | 0.04–0.08 s | list/grid reveals (tighter than feels natural) |
| Hover lift | `translateY(-1px)`, 140 ms | buttons |

Easing discipline: **`easeOut` for entrances, `easeIn` for exits, `easeInOut` for moves.** Never `linear`
except scroll-scrubbed progress. ([Motion easing](https://motion.dev/docs/easing-functions), [two easing curves](https://frigade.com/blog/two-easing-curves-no-animation-library))

### Smooth scroll — Lenis (marketing + report pages only)

- **What/why:** [Lenis](https://github.com/darkroomengineering/lenis) interpolates scroll → momentum/weight; the single most-copied trait of award-site feel. Use the `lenis` package (the `@studio-freight/*` packages are deprecated). ([npm](https://www.npmjs.com/package/lenis), [Next.js setup](https://bridger.to/lenis-nextjs))
- **Config:** `duration:1.2`, expo-out easing, `anchors:true`, `syncTouch:false` (smoothing touch feels *worse* at 390px — leave native).
- **Gotchas:** `"use client"` provider in `useEffect`; Lenis does **not** auto-respect reduced-motion — gate it (`lenis.destroy()` when the query matches). Works transparently with Motion's `useScroll`.
- **Critical:** do **NOT** apply Lenis to the decision-log scroll container. An SSE list that auto-scrolls to bottom fights Lenis's interpolation. Keep that pane on native `overflow-y:auto`; let Lenis own only the marketing/report document scroll.

### Route / page transitions — View Transitions API (native, Next 16)

- **What/why:** Browser snapshots old+new DOM and animates between them — shared-element morph is the single highest "this app is expensive" cue, now declarative. ([Next.js VT guide](https://nextjs.org/docs/app/guides/view-transitions), [React `<ViewTransition>`](https://react.dev/reference/react/ViewTransition))
- **Enable:** `experimental: { viewTransition: true }` in `next.config.ts`; `import { ViewTransition } from 'react'`. Same-document transitions are Baseline (Chrome 111+, Safari 18+, Firefox 144+); cross-document is Chrome-only — treat as progressive enhancement (zero-cost fallback: it just doesn't animate).
- **The highest-payoff use for you:** a run card in the history rail → the full run/report view (shared-element morph). Also tab/filter crossfades within the log/report.
- **Tuned values (steal these):** morph 400 ms with a mid-flight `blur(3px)`; **asymmetric exit 150 ms / enter 210 ms** (the premium tell); directional slide offset 60 px. Set `default="none"` per `<ViewTransition>` or everything animates. Add a `@media (prefers-reduced-motion: reduce)` block zeroing `::view-transition-*` durations — directional slides are the top motion-sickness trigger.
- **Don't double up:** if a boundary uses `<ViewTransition>`, don't also wrap it in Motion `<AnimatePresence>` page transitions. One per boundary.

### Scroll-driven reveals — pick the right tool

- **Decorative reveals on marketing/report** → native CSS `animation-timeline: view()` behind `@supports (animation-timeline: scroll())` (off-main-thread, free; author a fallback inside `@supports` because **Firefox is the gap**). ([MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll-driven_animations))
- **Anything that must match in Firefox or couples to React** → Motion `useScroll` + `useTransform` (uses native `ScrollTimeline` where possible, JS fallback otherwise). ([Motion scroll](https://motion.dev/docs/react-scroll-animations))
- **Simple "fade in once" inside the app** → your existing `Reveal` / Motion `whileInView viewport={{once:true}}`. You already do this — fine.

### GSAP — add *only* where it beats Motion

[GSAP is now 100% free including commercial use](https://gsap.com/pricing/) (Webflow acquisition; SplitText, MorphSVG, DrawSVG all unlocked, locked in 3.13). Don't default to it — add it surgically for:
- **Editorial text reveals** — `SplitText` with `mask:"lines"` + `autoSplit` (re-splits on font-load/resize, solving the FOUT reflow). The premium move for a Fraunces headline revealing line-by-line. ([Codrops demos](https://tympanus.net/codrops/2025/05/14/from-splittext-to-morphsvg-5-creative-demos-using-free-gsap-plugins/))
- **Botanical SVG line-art** drawing itself in (`DrawSVG`) or morphing (`MorphSVG`) — Motion can't morph arbitrary paths.
- **Scrubbed scroll storytelling** (`ScrollTrigger` with `scrub`).
- Use the `@gsap/react` `useGSAP()` hook (handles React 19 / StrictMode cleanup), `"use client"`, `gsap.matchMedia()` for reduced-motion. Code-split it — GSAP core + 2 plugins ≈ 40–60 KB. Keep Motion for component enter/exit, layout, drag, React-state-coupled animation.

### Micro-interactions worth adding

| Interaction | How (this stack) | Gotcha |
| --- | --- | --- |
| **Number tickers** (sources consulted, experts spawned, token budget) | Motion's first-party `<AnimateNumber>` (zero new dep) or [`@number-flow/react`](https://number-flow.barvian.me/) | use Tailwind `tabular-nums` so width doesn't reflow; snap to final value under reduced-motion |
| **Card hover-glow** (Linear/Vercel feel) | DIY: `mousemove` writes `--x/--y` CSS vars → `radial-gradient` at cursor. No library, no React re-render | desktop-only — degrades to nothing on touch; throttle to rAF |
| **Magnetic buttons** | Motion `useMotionValue` + `useSpring` on translate, capped ~10–20% of cursor offset | gate behind a fine-pointer media query so it never fires at 390px; disable under reduced-motion |
| **Animated gradient accents** | CSS `@property` typed angle + `conic-gradient` (no JS), animate colors in **oklch** (Motion v12 supports oklch interpolation — perceptually smooth on your green palette) | `@property` unsupported in Firefox → static fallback; pause under reduced-motion |

([Premium micro-interactions without jank](https://dev.to/markyu/premium-micro-interactions-in-react-19-without-the-jank-230b))

---

## 2. Visual effects & atmosphere

You already ship grain (`feTurbulence`), `.glass`, and the `.stage` atmosphere. The research validates all
three. The delta is depth/shadows, backgrounds, and *one* optional hero shader.

### Depth & shadows — the highest-ROI visual upgrade (Tier 0)

This is what separates "tech template" from "considered design system," and it's nearly free.

- **Layered multi-shadow tinted with your palette, not black.** Stack 3–4 shadows at increasing offset/blur. For your botanical brand, a **moss-tinted** shadow (~30% tint, OKLCH) reads warmer and more intentional than black. Define as `@theme` `--shadow-*` tokens so every surface inherits them. ([Rauno — Designing Depth](https://rauno.me/craft), [box-shadow techniques](https://www.studiolimb.com/guides/css-box-shadow-techniques.html))
- **Tailwind v4 native:** `inset-shadow-*` and `inset-ring-*` let you stack up to four colored shadow layers — a faint top-edge inner highlight + bottom shadow makes buttons/inputs feel lit and tactile. ([Tailwind v4 shadows](https://tailwindcss.com/docs/box-shadow))
- **1px gradient-hairline top edge** (lighter at top) simulates a light source = instant depth. Fits your existing hairline/ledger aesthetic.
- **Per-theme shadow tokens** (see §6) — a single shadow value silently breaks dark mode. This is the #1 cheap-dark-mode tell.
- **Perf:** never animate `box-shadow` (repaints). For hover-lift, animate `transform` and cross-fade a pre-rendered shadow layer (`::after` opacity).

### Backgrounds — the Linear/Vercel look, zero JS (Tier 0)

- **Dot grid / line grid + radial-fade mask.** Pure CSS, SSR-safe, the Vercel signature:
  ```css
  background-image: radial-gradient(var(--dot) 1px, transparent 1px);
  background-size: 16px 16px;
  mask-image: radial-gradient(ellipse 50% 50% at 50% 50%, #000 60%, transparent 100%);
  ```
  Tailwind v4 has first-class `mask-*` utilities. Drive `--dot` from a theme token. ([grid & dot backgrounds](https://ibelick.com/blog/create-grid-and-dot-backgrounds-with-css-tailwind-css))
- Combined with your existing grain overlay, that two-layer combo *is* the premium-SaaS backdrop with zero JS.

### Mesh / aurora — cheap ambient, gated (Tier 1/2)

- **CSS aurora blobs:** 3–4 absolutely-positioned blurred radial gradients, `transform`-animated. Resolution-independent, great LCP. Keep blob count low and animate transform/opacity only; gate animation behind reduced-motion (render static when reduced). ([Auroral](https://lunarlogic.github.io/auroral/))
- Use sparingly and low-contrast (8–20s loops) or it distracts and drains battery.

### One signature hero shader — optional, lazy, gated (Tier 2)

- **[Paper Shaders](https://shaders.paper.design/)** (`@paper-design/shaders-react`) — zero-dependency canvas shaders (`MeshGradient`, `GrainGradient`, `Dithering`), built-in perf caps (`minPixelRatio`, `maxPixelCount`, `fit`). This is the 2026 look replacing the Stripe gradient.
- **Rules:** `next/dynamic({ ssr:false })` behind a CSS gradient placeholder; `useReducedMotion()` → swap to `StaticMeshGradient` / `speed={0}`; IntersectionObserver pause offscreen; cap pixel ratio on mobile. License: PolyForm Shield (free commercial; only restriction is you can't build a competing shader tool — fine for you).
- **Use on the hero only.** Avoid Spline and heavy R3F for ambient backgrounds — they tank Core Web Vitals.

### Glassmorphism posture (you already have `.glass`)

Keep it **sparing** — composer bar, floating status panel, popovers — over a controlled backdrop. Never as the
page foundation (translucency can pass contrast on one screen and fail on another). Always ship the `-webkit-`
prefix + a solid `@supports not (backdrop-filter: blur(1px))` fallback. `backdrop-filter` is one of the most
expensive paints — never animate a glass surface while a gradient animates behind it. Don't chase Apple's
"Liquid Glass" (real refraction isn't reproducible in browsers). ([Liquid Glass vs glassmorphism](https://www.setproduct.com/blog/liquid-glass-vs-glassmorphism))

---

## 3. Typography & layout

Your type trio is already a premium editorial choice — **Fraunces** (with `opsz`/`SOFT`/`WONK` axes),
**Schibsted Grotesk**, **Spline Sans Mono**. This is better than 90% of SaaS. The delta is in *details*:
fluid scale, optical sizing, numeric features, and kinetic reveals.

### Fluid type & v4 wiring (Tier 0)

- **Fluid scale:** generate `clamp()` values at [Utopia.fyi](https://utopia.fyi/) and paste as `@theme`
  `--text-step-*` tokens (dependency-free, upgrade-safe). **Keep a `rem` term in the clamp middle**
  (`clamp(1rem, 0.93rem + 0.36vw, 1.25rem)`, never pure `vw`) so browser zoom still works (WCAG 1.4.4).
- **The #1 "font not applying" bug:** when mapping a `next/font` variable into Tailwind v4, use `@theme inline`
  (not plain `@theme`) so the utility inlines `var(--font-x)`. Verify your `globals.css` uses `inline`.
- **Optical sizing:** add `axes: ['opsz']` to the Fraunces `next/font` call (only `wght` ships by default),
  then `font-optical-sizing: auto`. You already request `opsz` — confirm it's wired to the utility.

### Premium type details (Tier 0)

- **`tabular-nums slashed-zero`** on every metric, the pricing table, token meters, timestamps — so digits
  don't reflow width while animating. `oldstyle-nums` in long-form prose.
- **`text-balance`** on hero headlines only; **`text-pretty`** on report prose (prevents orphans/rivers).
- **Tracking tokens:** tighten display (`--tracking-tight`), loosen mono eyebrow labels (you already have
  `.tag-label` small-caps — good). ([Next.js fonts](https://nextjs.org/docs/app/getting-started/fonts), [Tailwind v4 release](https://tailwindcss.com/blog/tailwindcss-v4))

### Kinetic / editorial reveals (Tier 2)

The premium "words animate in" = split into lines → mask-reveal (overflow-hidden wrapper, slide up from a hard
edge) → per-fragment stagger → slow expo-out. **The mask edge is the biggest premium signal.**

- **Recommended (no new dep, matches your "hand-built" rule):** hand-split + Motion variants +
  `staggerChildren` + `whileInView once`. Respect reduced-motion (Motion auto-reduces transforms but **not
  opacity** — use `useReducedMotion()` to collapse to instant; reduced-motion users must see fully-revealed
  text, never blank). Wait for `document.fonts.ready` before splitting or line breaks compute against the
  fallback font. SSR the un-split sentence (SEO + no flash), split client-side in an effect.
- **Graduate to GSAP SplitText** only if masked typography becomes a signature — its `autoSplit` handles the
  font-load/resize re-split cleanly.
- **Avoid** Aceternity `TextGenerateEffect` and Magic UI blur-in — the most recognizable "AI landing page" clichés.

---

## 4. Streaming / agent UX — the centerpiece

This is where most of the premium budget should go. It is your strongest "expensive software" asset. Your
current pieces: `decision-log.tsx` (ledger transcript), `run-activity.tsx` (collapsed "thinking" verb line),
`expert-panel.tsx`, `report.tsx` (react-markdown streaming), `hydration-panel.tsx`, folded by
`useLiveRun`/`foldRunEvent`.

### 4.1 Report rendering — upgrade the renderer (Tier 0)

Your `report.tsx` uses `react-markdown` + `remark-gfm`, correctly omits `rehype-raw`, and drops images (XSS-safe
— keep that posture). Two upgrades:

- **Smooth-stream character buffering** — *pure client, no backend change, biggest perceptual win.* Decouple
  network arrival from visual reveal: buffer incoming `report_delta` chunks, drain to screen at a constant rate
  via `requestAnimationFrame` (~one char/5 ms, or word-chunked at ~30–100 ms). Eliminates bursty "text appears
  in chunks" jank and smooths over network/429 pauses so the agent never *looks* stalled. ([Smooth streaming](https://upstash.com/blog/smooth-streaming), [why React lags with streaming text](https://akashbuilds.com/blog/chatgpt-stream-text-react))
- **Block-memoized rendering** — split the accumulating markdown with the `marked` lexer, render each block in
  `React.memo` with **index-based keys**; only the last (actively-written) block re-parses. Wrap the
  block-state update in `startTransition`. This is the difference between buttery and stuttering on a 2000-word
  report. ([performant AI markdown renderer](https://tigerabrodi.blog/how-to-build-a-performant-ai-markdown-renderer), [AI SDK memoization cookbook](https://ai-sdk.dev/cookbook/next/markdown-chatbot-with-memoization))

**Optional bigger move — [Streamdown](https://streamdown.ai/):** a drop-in `react-markdown` replacement *built*
for streaming. It styles incomplete markdown gracefully (open `**`, half code fences), ships Shiki
highlighting + KaTeX + Mermaid, copy/download buttons, and hardens untrusted image/link origins by default via
`rehype-harden`. It takes a plain string — **you do not need the Vercel AI SDK**; feed it your accumulated SSE
text. If you adopt it: add `@source "../node_modules/streamdown/dist/*.js"` to your Tailwind v4 CSS (or its
classes silently don't apply) and map your `theme.config.ts` tokens onto its shadcn-style CSS vars
(`--background`/`--foreground`/`--primary`/`--radius`). ([Streamdown repo](https://github.com/vercel/streamdown))
*Recommendation:* if you want Shiki/KaTeX and robust incomplete-markdown handling, adopt Streamdown and skin
it; otherwise the smooth-stream + block-memo upgrade on your existing renderer is enough for Tier 0.

### 4.2 Parallel-expert swimlanes (Tier 1 — needs `CONTRACT.md` §2.2/2.3)

This is where your **entropy spawn-count math becomes visible** and premium. Reference products: Anthropic
Claude Research (lead agent plans, spawns 3–5 parallel subagents that act as filters), Manus's "Computer" view
with a live `todo.md` checklist, Perplexity's parallel async sub-agents. ([Anthropic multi-agent system](https://www.anthropic.com/engineering/multi-agent-research-system), [Manus](https://manus.im/blog/manus-browser-operator))

- One **lane per expert**, keyed on `agentId`, showing: domain/role, status pill (`queued → running → done`),
  current tool, a tiny progress bar, optional confidence dot.
- The instant the `plan` event arrives, render N lanes as skeletons (don't wait for each expert to start) —
  this makes the spawn decision feel deliberate and "alive."
- **Hand-build it in Motion v12** (not a chart lib): `layout="position"` + `AnimatePresence mode="popLayout"`
  so lanes appear/complete/reflow smoothly. Reads bespoke, on-theme, near-zero bundle. Requires stable
  `agentId` keys (CONTRACT §2.1).
- Optionally show `spawnReason.entropy` as a one-line caption ("3 experts · domain entropy 1.8 bits"). This is
  a differentiator, not debug output.

### 4.3 Decision log — keep it, harden the motion (Tier 0/1)

Your ledger is good and matches the "Stream of Thought" pattern (explicit step states, collapsible, nested
content). ([Shape of AI — Stream of Thought](https://www.shapeof.ai/patterns/stream-of-thought)) The motion
caveats from the research:

- New row enters: `opacity 0→1` + `translateY(8px→0)`, **200 ms ease-out**, stagger only on *initial* mount
  (don't re-stagger on every append).
- Use `AnimatePresence mode="popLayout"` + per-item `layout="position"` (not `layout` on the container) — so
  your condense/recall feature reflows smoothly.
- **No per-row `will-change`, no springs-per-event, no blur filters on the list.** Dozens of streaming rows
  with bouncy springs will look chaotic and chew main-thread time. Save expensive motion for the report reveal.
- **Virtualize** the log once it's long (TanStack Virtual) — see §7.

### 4.4 Tool-call cards (Tier 1 — CONTRACT §2.4)

Render tool calls as collapsible cards (input args → output → status/error), auto-open while running. Lift the
*structure* from [Vercel AI Elements](https://github.com/vercel/ai-elements) `Tool` or [prompt-kit](https://www.prompt-kit.com/docs/tool) `Tool` (MIT, you own the source) and re-skin to Botanical.

### 4.5 Citations — the Perplexity pattern (Tier 1 — CONTRACT §2.5)

The gold standard: numbered inline `[n]` chips bonded to claims; a sidebar of source cards; cards slide in as
citations generate; hovering a citation highlights the matching card and pops a preview (favicon/title/snippet);
**all transitions ≤200 ms.** ([Perplexity citations case study](https://www.aiuxplayground.com/gallery/perplexity-citations/), [Shape of AI — citations](https://www.shapeof.ai/patterns/citations))

- Inline chips require the report text to carry citation markers tied to `sourceId` (CONTRACT §2.5) — the
  frontend can't reconstruct the claim↔source bond. Render markers as chips via a custom renderer component.
- Hover cards: Radix/Base UI HoverCard, 200 ms in/out, favicon + title + snippet + domain.
- Lift `InlineCitation` + `Sources` structure from AI Elements / [shadcn AI](https://www.shadcn.io/ai/inline-citation) and skin it.

### 4.6 The report-reveal moment (Tier 1 — CONTRACT §2.6/2.7)

Make the deliverable feel like a *payoff*, not another chat bubble. On the `phase: "delivering"` event:

- Collapse the live work view into a compact summary, then fade/slide the report into a centered reading
  column — a clear phase transition signals "research done, here's your report." (AI Elements `Artifact`
  encodes this framing.)
- **Sticky TOC** built from the `report_outline` event with IntersectionObserver active-section highlight
  (doubles as a progress indicator). ([sticky TOC](https://css-tricks.com/sticky-table-of-contents-with-scrolling-active-states/))
- **Reading-progress bar** (`scrollTop / (scrollHeight - clientHeight)`). ([reading progress bar](https://blog.logrocket.com/creating-reading-progress-bar-react/))
- **Export** (PDF) — server-side render of the final immutable HTML keeps parity (out of frontend scope, but
  wire the button).
- Your existing `.dropcap` / `ornate` drop-cap on delivered reports is a nice payoff detail — keep it.

### 4.7 Skeletons & "alive" loading (Tier 0/1)

Skeletons are perceived as up to ~50% faster than spinners; past 5 s a spinner reads as "broken" — and your
runs are ~38 s+, so this is non-negotiable. ([skeleton vs spinner](https://www.onething.design/post/skeleton-screens-vs-loading-spinners)) The premium move: skeleton the **actual structure** (N expert lanes appear
the instant the orchestrator decides N — CONTRACT §2.2), not a generic gray box. Keep shimmer slow (1.5–2 s).

---

## 5. Headless primitives & components to adopt

You hand-build components (correct — keeps the design un-templated). Use **headless** primitives for
accessible, polished *behavior* you skin with your own tokens, and lift *patterns* (not runtimes) from AI kits.

### Primitives worth standardizing on

| Primitive | Use | Note |
| --- | --- | --- |
| **[Base UI](https://base-ui.com/)** | new accessible primitives (combobox, popover, dialog, etc.) | from the Radix + Floating UI + MUI teams; stable v1.0 (Dec 2025), actively funded. **Prefer over Radix for new work.** Docs recommend Motion for animation. |
| **[Vaul](https://github.com/emilkowalski/vaul)** | mobile drawer / bottom-sheet (drag, snap points) | serves your phone-first mandate; verify React 19 peer dep (or use Base UI's Drawer) |
| **[Sonner](https://sonner.emilkowal.ski/)** | toasts | best-in-class; theme to Botanical via `classNames` |
| **[cmdk](https://github.com/pacocoursey/cmdk)** | ⌘K command palette | you already have `command-palette.tsx` — cmdk is the canonical engine; the palette itself is a "serious pro tool" signal |
| **[TanStack Table + Virtual](https://tanstack.com/virtual)** | findings/citations/history; virtualize the decision log | headless, 60fps on huge lists — directly relevant to §4.3 and §7 |
| **[Floating UI](https://floating-ui.com/)** | bespoke anchored UI (citation hovercards, status popovers) | the positioning engine under Radix/Base UI |

All are unstyled, `data-*`-driven, need `"use client"` on interactive parts, work with React 19 + Tailwind v4 +
Motion v12.

### AI component kits — lift patterns, not runtimes

- **[Vercel AI Elements](https://github.com/vercel/ai-elements)** (MIT, shadcn-registry, you own the source) —
  the best *structural* reference for `Reasoning`, `Task`/`Plan`, `Agent`, `Tool`, `InlineCitation`, `Sources`,
  `Artifact`. Take the component structure; ignore its Vercel-AI-SDK data layer (you're on PydanticAI + custom
  SSE). Re-skin to Botanical.
- **[prompt-kit](https://www.prompt-kit.com/)** — clean Tailwind-native `Message`/`Reasoning`/`Tool`/`PromptInput`; backend-agnostic, good fit for your hand-built theme.
- **[assistant-ui](https://github.com/assistant-ui/assistant-ui)** — only if you want its AG-UI runtime to avoid writing the client event-reducer yourself (you already have `foldRunEvent`, so likely skip).
- **Avoid adopting CopilotKit's full runtime** — it would fight your custom theme/architecture.

### Theming leverage

- **[tweakcn](https://tweakcn.com/)** — run your Botanical palette through it → OKLCH `@theme` tokens, so any
  borrowed component inherits Clannon's skin automatically. Highest-leverage re-theme step.

### Registry honesty (the "AI template" smell lives in the *default skin*, not the code)

Use as **re-themeable base:** Origin UI (deep app-UI, Tailwind v4), Tremor (dashboards/charts), Motion
Primitives (restrained editorial motion — on-brand for you). **Garnish only, one re-skinned primitive at a
time:** Aceternity (ban the 3D card flip / Vortex / Globe), Magic UI (its **Animated Beam** genuinely fits
visualizing experts fanning out; **Number Ticker** for metrics; avoid Shimmer Button). **Skip the 21st.dev
Magic generator** (security advisory — see `AGENT_TOOLING.md`).

---

## 6. Finishing touches

### Theme polish (Tier 0)

- **Per-theme shadow + surface tokens.** Add a 4-level surface scale (base / raised / overlay / modal) to
  `theme.config.ts`; dark mode = lighter surfaces (step +5–8% L per level) with near-zero shadows, light mode =
  per-level shadow tokens. A single shadow value silently breaks dark mode — the #1 cheap-dark-mode tell.
  ([dark mode systems](https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/))
- **OKLCH everywhere** (Tailwind v4 default). Reduce chroma / raise L for dark-mode accents (saturated accents
  vibrate on dark). Derive states via relative color: `oklch(from var(--accent) calc(l + 0.1) c h)`.
  ([OKLCH](https://evilmartians.com/chronicles/oklch-in-css-why-quit-rgb-hsl))
- **View-Transitions circular theme reveal** — the signature 2024-26 theme-toggle effect, now Baseline
  (Oct 2025). `document.startViewTransition(() => flushSync(() => setTheme(next)))` then animate `clip-path:
  circle()` from the toggle's center to the far corner (`Math.hypot`). Early-return on reduced-motion / no
  support. ([full-page theme toggle](https://akashhamirwasia.com/blog/full-page-theme-toggle-animation-with-view-transitions-api/)) **Deconflict:** if you use this, don't run next-themes `disableTransitionOnChange` alongside it — let the VT API own the animation. (You manage theme in `theme.tsx` today; the same pattern applies.)
- **`theme-color` meta per scheme** via the `viewport` export (not the deprecated `metadata.themeColor`),
  colors from `theme.config.ts` — mobile browser chrome matching your canvas reads as "real app."

### Accessibility *as* premium (Tier 0)

- **Pre-mounted `aria-live="polite"` milestone announcer.** Mount one empty live region at shell load, push
  milestone text into it ("synthesis started", "report ready"). Do **not** create the node when results arrive
  — the #1 cause of dead live regions. Debounce; don't announce every token. Almost no AI streaming UI ships
  this — it's a craft signal. (You already have `aria-live` on the log scroll region — extend it to milestones.)
  ([ARIA live regions](https://k9n.dev/en/blog/2025-11-aria-live/))
- **`:focus-visible` rings** driven by a `--color-focus` token (you have rings — make them per-theme,
  prefer `outline` over `ring` in v4 so `overflow-hidden` doesn't clip them, 3:1 min contrast).
- **Contrast:** ship to WCAG 2.2 AA (legal floor — EU Accessibility Act in force since June 2025) but design
  dark mode to APCA Lc (WCAG 2.x overstates contrast near black). ([Why APCA](https://git.apcacontrast.com/documentation/WhyAPCA.html))
- **44px touch targets** via `pointer-coarse:` (dense on desktop, comfortable on touch from one component).
- **`forced-colors:` / `contrast-more:`** variants — shadow-only elevation vanishes in Windows High Contrast,
  so always have a border fallback.

### Sound & haptics (Tier 2 — both default-OFF, sticky, reduced-motion-gated)

- **Sound:** map to the *outcome* layer only (run completes, report ready, verify fails) — never routine
  clicks. Stripe/Linear/Vercel ship no UI sound; restraint is the premium move. Use
  [`use-sound`](https://www.joshwcomeau.com/react/announcing-use-sound-react-hook/) (lazy-loads Howler) or
  [`sounded`](https://github.com/PlebsNet/sounded) (theme-aware packs + built-in localStorage mute). Default
  OFF for a B2B tool; treat `prefers-reduced-motion: reduce` as sound-off too. Ship 4–5 sounds in one key as a
  single sprite. **Highest-value moment: run completion** (warm chime + visual celebration).
- **Haptics:** [`navigator.vibrate`](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/vibrate) is
  **Android Chromium only** in 2026 (Safari never shipped, Firefox removed it). Feature-detect
  (`'vibrate' in navigator`), use the [`web-haptics`](https://github.com/lochie/web-haptics) semantic wrapper,
  gate by the same toggle. Light = selection, medium = primary CTA, heavy = error. Never load-bearing.

### Empty / error / 404 states (Tier 0/1)

- **Empty state = your onboarding surface.** Strongest lever for an AI tool: a **pre-populated sample report**
  (real decision log + report, labelled "sample") — delivers the aha *before* any token spend. You already have
  demo briefs/`WORKSPACE_EXAMPLES` — extend that into a one-click sample run. ([SaaS empty states](https://www.eleken.co/blog-posts/empty-state-ux))
- **Next 16 error files (most tutorials are stale):** `error.tsx` recovery prop is now `unstable_retry` (not
  `reset`), must be `"use client"`; place a granular boundary around the run view; SSE/fetch failures aren't
  caught by boundaries — handle manually (you already have failure/reconnect banners — good). `global-error.tsx`
  must render its own `<html>`/`<body>`. ([Next error handling](https://nextjs.org/docs/app/getting-started/error-handling))
- **404 (`not-found.tsx`):** large editorial number + on-brand quip + recall/search + route home. Not a game.

### Microcopy (Tier 0, ongoing)

Stripe is the reference voice: lowercase verb-object CTAs ("Start research"), no exclamation marks, no
"revolutionary/seamless," errors as clinical diagnosis + the fix. For AI status, two registers: concrete
progress ("Searching 4 sources", "1 of 5 experts reported") or sparing reassurance on long waits. Your existing
"calling experts" (vs "calling a tool", commit 3e45ac8) is exactly the right register — domain-honest, no
mascot. Never "thinking hard…". ([3 i's of microcopy](https://www.nngroup.com/articles/3-is-of-microcopy/))

### Favicon / PWA / OG (Tier 2)

- **Favicon:** `icon.svg` (dark-mode-capable via embedded `@media`) + `favicon.ico` + 180 apple-touch + 192/512
  PNG + 512 maskable, dropped into `app/` (Next auto-tags). Safari ignores the SVG dark query → PNG fallback
  covers it. **No animated favicon for branding** (throttled to ~1fps in background tabs); the one defensible
  use is a transient run-progress badge.
- **OG images:** `ImageResponse` from `next/og` in `opengraph-image.tsx` (you already have one). Premium =
  dynamic per-report OG. **Flexbox only, no `display:grid`**; Tailwind via the `tw` prop; must set
  `metadataBase`. ([Next metadata/OG](https://nextjs.org/docs/app/getting-started/metadata-and-og-images))
- **PWA:** typed `app/manifest.ts` (you have one) + a maskable 512 icon. No `next-pwa` (unmaintained); Serwist
  doesn't support Turbopack (needs `--webpack`). iOS push only for installed PWAs.

### Pricing / marketing page (Tier 2 — you want to charge more, so this matters)

- **Three tiers, highlight the middle (Pro $79 "Most Popular"), anchor with Agency $199.** Annual/monthly
  toggle, default annual. ([anchoring psychology](https://www.getmonetizely.com/articles/how-does-anchoring-psychology-shape-customer-decisions-on-your-saas-pricing-page))
- **You bill on token budgets, not report counts** → state budgets plainly + add an **interactive usage
  estimator** in the card (Vercel does this; strong fit for usage-based billing).
- **Trust copy from your security pipeline:** reframe ClamAV/YARA + sanitization + verifier LLM + user-scoped
  data as trust signals (real differentiator even pre-certification). Add SOC2/GDPR badges when available.
- **The "expensive software" aesthetic** (Linear/Vercel/Stripe/Raycast): dark default + one restrained accent
  (your green), generous whitespace, large serif/text heroes, grain overlay, sparing scroll-reveal. Your
  Botanical/Editorial system already nails most of this. **The most convincing product shot you have is your
  own animating streaming decision-log + report** — feature it on the landing page (you already have a hero-demo
  teaser; make it the centerpiece). ([The Linear Look](https://frontend.horse/articles/the-linear-look/))

---

## 7. Performance *as* premium

Fast == premium. Only ~56% of origins pass all three Core Web Vitals — passing is itself a differentiator, and
**INP ≤ 200 ms** is the one that matters most for an interactive streaming app (a laggy tap is the single most
"cheap-feeling" thing a web app does). ([web.dev INP](https://web.dev/articles/inp))

- **React Compiler (stable 1.0)** — `reactCompiler: true` + the ESLint plugin auto-memoizes; Meta reports >2.5x
  faster interactions, 25–40% fewer re-renders, zero code changes. Lowest-effort INP win. (Babel → slower
  builds; measure.) ([React Compiler](https://react.dev/learn/react-compiler/introduction))
- **Virtualize the decision log + history rail** (TanStack Virtual). A streaming log that appends every few
  hundred ms over a long run will blow INP without virtualization. Also wrap streamed state updates in
  `startTransition` (interruptible, drops stale intermediate renders).
- **PPR / Cache Components (stable in Next 16)** — `cacheComponents: true` + `"use cache"`: the editorial shell
  becomes a static edge-cached instant paint; per-user run data streams into `<Suspense>` holes. Your single
  biggest "instant load" lever, and it maps cleanly onto multi-tenancy. ([Next 16 release](https://nextjs.org/blog/next-16))
- **Font CLS landmine:** `next/font` computes fallback metrics against the **first weight imported** — your 700
  Fraunces headline (likely the LCP element) can still shift if you load 400+700. Fix: use the variable font
  (you do) or a separate `next/font` instance per weight. ([next/font](https://vercel.com/blog/nextjs-next-font))
- **Bundle discipline:** `optimizePackageImports`, kill barrel-file imports (a `components/index.ts` barrel
  defeats tree-shaking), `@next/bundle-analyzer` per release, `next/dynamic` for charts/markdown/3D/GSAP.
- **Motion bundle:** `motion` ≈34 KB; `LazyMotion` + the slim `m` component (`domAnimation`, +15 KB, `strict`)
  trims it if size bites. Animate only `transform`/`opacity` (you mostly do).
- **Verify (frontend-observable):** the SSE stream isn't buffered by the host/proxy (a buffering proxy silently
  kills the entire streaming-premium story — flag to backend, see `BACKEND.md`); clean console (no hydration
  warnings); LCP/INP/CLS in budget. Use the Chrome DevTools MCP `lighthouse_audit` loop (`AGENT_TOOLING.md`).

---

## 8. Recommended rollout

Mirrors `README.md`. **Tier 0 needs zero backend changes** — start there:

1. **Tier 0 (pure client):** smooth-stream + block-memo report render · tinted layered + per-theme shadow
   tokens · fluid type + tabular-nums + optical sizing · VT theme-reveal · `aria-live` milestones · React
   Compiler + virtualized log · sample-report empty state.
2. **Tier 1 (coordinate via `CONTRACT.md`):** expert swimlanes · inline citations + hover cards · report-reveal
   + TOC + reading progress · token-budget/confidence meters · structure-shaped skeletons · `seq` reconnect dedup.
3. **Tier 2 (signature):** one lazy hero shader · kinetic headline · sound + haptics · PPR shell · pricing-page pass.

Build Tier 1 against the **mock first** (it's the contract's source of truth) so the premium UI is demoable
before the backend ships the data.
