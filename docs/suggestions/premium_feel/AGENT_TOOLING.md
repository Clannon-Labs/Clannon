# AGENT TOOLING — what the AI agent uses to BUILD and VERIFY premium UI

> This is the meta layer the user explicitly asked for: the **tools, skills, plugins, and MCP servers** an AI
> coding agent (Claude Code) can leverage to design, build, and iterate on a premium frontend. It is not
> frontend or backend application code — it's the *toolchain*. Verified against primary sources, June 2026.
> Version-sensitive items are flagged; re-check before relying on exact commands/pricing.

**The spine (install these three):** the **`frontend-design` skill** (taste), the **shadcn MCP** + a premium
registry or two (components), and a **Playwright + Chrome DevTools MCP** loop (so the agent can *see* its own
output and iterate). Everything else is leverage on top.

A security note up front, given your posture: **treat any "generate-and-paste" tool as untrusted input.**
Read-only doc/registry MCPs are fine; code generators have a real prompt-injection surface (the 21st.dev Magic
MCP has an open advisory — see below). Review generated code before it lands.

---

## PART 1 — Tools the agent uses to BUILD

### 1A. Taste & design philosophy (Claude Code skills/plugins)

**`frontend-design` skill (Anthropic, official) — the single highest-leverage item.**
- Makes Claude declare an aesthetic direction (purpose, tone, constraints, differentiation) *before* writing
  CSS, then implement with deliberate type, a 4–6 named-token palette, orchestrated Motion, and grid-breaking
  composition. Explicitly bans generic "AI slop" defaults (Inter/system fonts, `01/02/03` markers, templated
  hero layouts). Maps cleanly onto your existing token-based Botanical system. Model-invoked automatically on
  any "build/redesign UI" request.
- Install: `/plugin install frontend-design@claude-plugins-official` (the official marketplace is auto-available),
  or pull the raw skill folder into `.claude/skills/`. Source: `anthropics/claude-code/plugins/frontend-design/`.
  Free, Apache-2.0. ([plugin](https://claude.com/plugins/frontend-design), [repo](https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design))

**Author a project skill that encodes the Botanical Archive rules.** Create
`.claude/skills/clannon-botanical-design/SKILL.md` (use the `skill-creator` meta-skill) so every agent stays
on-brand without bloating `CLAUDE.md` — auto-loaded, on-demand, context-cheap. The
[`anthropics/skills`](https://github.com/anthropics/skills) repo has reusable frontend skills worth mining:
`theme-factory` (includes a "Botanical Garden" preset), `brand-guidelines`, `web-artifacts-builder`,
`webapp-testing`. Install: `/plugin marketplace add anthropics/skills`.

**Community frontend subagent rosters** (two-step: `/plugin marketplace add owner/repo` →
`/plugin install <name>@<marketplace>`):
- [`wshobson/agents`](https://github.com/wshobson/agents) (MIT) — `frontend-developer`, `ui-ux-designer`,
  `design-system-architect`, `accessibility-expert`, `ui-visual-validator`.
- [`VoltAgent/awesome-claude-code-subagents`](https://github.com/VoltAgent/awesome-claude-code-subagents) — its
  `design-bridge` agent translates a `DESIGN.md` design-system doc into faithful UI instructions (useful for
  enforcing the Botanical look across agents).
- Official guidance to follow: the ["Prompting for frontend aesthetics" cookbook](https://platform.claude.com/cookbook/coding-prompting-for-frontend-aesthetics)
  (recommends the Motion library — which you already use) and the screenshot→implement→diff→fix loop in
  [best practices](https://code.claude.com/docs/en/best-practices).

### 1B. Components & theming (the shadcn registry ecosystem)

The ecosystem converged on one mechanism: the **shadcn CLI + registry protocol.** The agent installs *any*
component (free/paid, first/third-party) via `npx shadcn@latest add <url-or-@namespace/name>`; components land
as **owned source** — ideal for re-skinning to Botanical.

**Official shadcn MCP server** — lets the agent browse/search/install across configured registries in natural
language. Add: `npx shadcn@latest mcp init --client claude`, or `.mcp.json`:
```json
{ "mcpServers": { "shadcn": { "command": "npx", "args": ["shadcn@latest", "mcp"] } } }
```
Free, MIT. ([docs](https://ui.shadcn.com/docs/mcp), [registry protocol](https://ui.shadcn.com/docs/registry))

**Premium registries to add to `components.json`** (pull selectively, re-skin on contact):

| Library | Best for | Note |
| --- | --- | --- |
| [Origin UI](https://originui.com/) | deep, accessible app-UI, Tailwind v4 | best "doesn't look templated" base |
| [Tremor](https://www.tremor.so/) | dashboard charts | for token/budget viz if you don't hand-roll |
| Motion Primitives | restrained editorial motion | on-brand for Botanical |
| [Aceternity](https://ui.aceternity.com/) | hero/marketing motion | **garnish only — ban 3D card flip / Vortex / Globe** |
| [Magic UI](https://magicui.design/) | micro-interactions | Animated Beam (experts fanning out), Number Ticker; avoid Shimmer Button |

Discovery index: [registry.directory](https://registry.directory/).

**[tweakcn](https://tweakcn.com/)** — visual theme generator for shadcn on Tailwind v4 (OKLCH, contrast checks).
Run your Botanical palette through it → publishes as a `registry:theme` the agent applies with
`npx shadcn@latest add <theme-url>`. Highest-leverage step for making every borrowed component inherit your
skin. Free, Apache-2.0. *(Exact MCP config / theme-URL pattern is JS-rendered on the site — verify at source.)*

### 1C. Design-to-code & generation

**Official Figma MCP server** (if you produce Figma designs) — reads real components, variables/tokens, layout,
and Code Connect mappings so generated code matches exact spacing/colors/names.
- Remote: `claude plugin install figma@claude-plugins-official` → authenticate (OAuth), endpoint
  `https://mcp.figma.com/mcp`.
- Desktop: enable MCP in Figma Dev Mode → `claude mcp add --transport http figma-desktop http://127.0.0.1:3845/mcp`.
- Beta, free during beta (remote works on all plans, free seats capped at 6 tool calls/mo; desktop needs a paid
  Dev/Full seat). ([docs](https://developers.figma.com/docs/figma-mcp-server/))
- Community alternative (no desktop app, token-based, CI-friendly):
  [`figma-developer-mcp` (Framelink)](https://github.com/GLips/Figma-Context-MCP) — `npx -y figma-developer-mcp --figma-api-key=KEY --stdio`.

**[v0 by Vercel](https://v0.app)** — strongest premium UI generation out of the box; produces idiomatic
Next.js + shadcn + Tailwind, your stack. Free tier (no API); Premium $20/mo. The **v0 Platform API** (`v0-sdk`,
`https://api.v0.dev`, `V0_API_KEY`) is scriptable but **requires a paid plan and has no MCP** (REST/SDK only).
Use as a *reference/scaffold* generator, then hand-tune to Botanical.

**Other design-to-code** (most are human-in-loop; output handed to the agent):
[Subframe](https://www.subframe.com) (deterministic React/Tailwind via `npx @subframe/cli sync` + a Claude
plugin — best agent fit besides Figma), [Builder.io Visual Copilot](https://www.builder.io/blog/visual-copilot-cli)
(codebase-aware, reuses your components), [html.to.design](https://html.to.design) (import any live site as
editable Figma layers — capture a premium reference, read it via Figma MCP).

### 1D. Assets

- **Icons:** you use `lucide-react` (ISC, great default). [Phosphor](https://phosphoricons.com/) adds 6 weights
  incl. duotone (premium differentiator). For any-icon-at-build-time:
  [`iconify-mcp-server`](https://github.com/imjac0b/iconify-mcp-server) (200k+ icons) —
  `claude mcp add iconify-mcp-server -- npx -y iconify-mcp-server@latest`.
- **AI illustration/image gen:** [fal.ai](https://fal.ai) or [Replicate](https://replicate.com) as aggregators;
  Flux 1.1 Pro (clean commercial terms) for heroes, Recraft V3 for vector/brand. Use sparingly — your editorial
  brand likely wants type + line-art over stock AI imagery.
- **Image optimization:** `next/image` + `sharp` (`npm i sharp` — required for `next start` or images ship slow).
- **OG images:** `next/og` (`ImageResponse` → PNG via Satori) in `opengraph-image.tsx` (you already have one).
- **Favicons:** `npx realfavicon generate` — full set + tags from one source, scriptable.
- **3D (marketing hero only, never ambient):** Spline + `@splinetool/react-spline`, lazy-loaded — highest
  wow/effort but heavy; the research advises against it for ambient backgrounds.

---

## PART 2 — Tools the agent uses to VERIFY / ITERATE

This is what turns a blind code generator into a self-correcting designer: **screenshot → critique → refine.**
This loop matters more than any single library for premium output.

**[Playwright MCP / CLI-Skill](https://github.com/microsoft/playwright-mcp) (Microsoft) — the agent's eyes.**
Real browser control: structured accessibility snapshots (deterministic interaction) + screenshots for visual
self-critique. Tools: `browser_navigate`, `browser_resize` (the 390px phone-first check), `browser_take_screenshot`,
`browser_snapshot`. Add: `claude mcp add playwright npx @playwright/mcp@latest`. Free, Apache-2.0.
*Note:* Microsoft now ships a CLI/Skill variant that's far more token-efficient than the MCP protocol — prefer
it for long refine sessions since Claude Code has shell access. *(The token-efficiency figures are a vendor
benchmark — directional.)*

**[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) (Google) — objective quality
gates.** Performance traces + Core Web Vitals, `lighthouse_audit` (a11y/SEO/perf scores), source-mapped
console (catches hydration warnings), network, device emulation. Add:
`claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest`. Free, Apache-2.0. Turns fuzzy "is
this premium?" into pass/fail gates — a11y score, clean console, LCP/INP/CLS budgets (ties directly to
`FRONTEND.md` §7).

> Playwright = *driving* (act, screenshot, resize, cross-browser). Chrome DevTools = *auditing* (why it's slow,
> how it scores). Run both. Skip the deprecated `@modelcontextprotocol/server-puppeteer`.

**Accessibility:** [`@axe-core/playwright`](https://playwright.dev/docs/accessibility-testing)
(`AxeBuilder().analyze()`) for machine-readable WCAG violations to drive auto-fix, plus the Chrome DevTools
`lighthouse_audit`.

**Visual regression — lock premium-ness once achieved:** Playwright
[`toHaveScreenshot()`](https://playwright.dev/docs/test-snapshots) — zero cost, baselines in git, agent reads
pass/fail + diff PNG directly. Graduate to [Argos](https://argos-ci.com/) (PR-inline diffs) for CI gating later.

**Capture reference sites (the "premium bar"):** [Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server)
— `firecrawl_scrape` returns a reference site's markup **and** a rendered screenshot the agent can analyze
against. (For your own localhost, Playwright/Chrome DevTools are already local and free.)

**Deploy/debug loop:** [Vercel MCP](https://vercel.com/docs/mcp/vercel-mcp) —
`claude mcp add --transport http vercel https://mcp.vercel.com` — closes the loop on your stated host (inspect
deployments, logs).

### The loop, concretely

```
npm run dev
  → browser_navigate localhost
  → browser_resize at 390 / 768 / 1440
  → browser_take_screenshot at each breakpoint
  → structured visual critique (spacing rhythm, type hierarchy, alignment,
    contrast, CTA dominance, overflow), optionally vs a Firecrawl-captured reference
  → objective gates: lighthouse_audit score, clean console, CWV in budget
  → edit Tailwind / theme.config.ts tokens
  → re-capture, repeat until visual critique AND gates pass
  → write a toHaveScreenshot() baseline so future regressions fail CI
```

Use the Playwright **CLI/Skill** here to keep context lean across many iterations.

---

## Recommended minimal toolchain for Clannon

1. **`frontend-design` skill** + a project `clannon-botanical-design` skill (taste, on-brand, context-cheap).
2. **shadcn MCP** + Origin UI / Motion Primitives (re-skin) + **tweakcn** to enforce the Botanical palette.
3. **Figma MCP** if you produce designs, or **v0** for premium scaffolds you then hand-tune.
4. **Playwright CLI/Skill + Chrome DevTools MCP** for the see-and-critique loop; **`toHaveScreenshot()`** to lock it.
5. **Vercel MCP** to close the deploy/debug loop.

## Caveats / verification notes

- **Verified vs primary sources:** shadcn MCP command, Figma MCP install (remote + desktop port 3845), Vercel
  MCP endpoint, Chrome DevTools MCP command/license, `frontend-design` plugin location + auto-invocation,
  `anthropics/skills` license.
- **Flagged uncertain (re-check before relying):** Playwright MCP-vs-CLI token figures (vendor benchmark); tweakcn
  exact MCP config + theme URL; v0 Platform API GA status (beta at last check); bolt.new/Polymet/html.to.design
  pricing.
- **Security:** **skip the 21st.dev Magic MCP generator** — open prompt-injection / supply-chain advisory and
  stalled maintenance. Treat all generate-and-paste output as untrusted; review before it lands. Read-only
  doc/registry MCPs (shadcn, Figma read, Firecrawl) are the safe default.
