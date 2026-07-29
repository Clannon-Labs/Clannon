# Clannon — frontend

The web dashboard for Clannon: marketing site, auth, and the research
workspace (live decision log, memory archive, settings). Next.js 16 App
Router, Tailwind v4, TanStack Query.

Naming: **Clannon** is the product (everything user-facing). **Vraksha**
is the backend engine it talks to — the name only appears where the
code refers to the engine itself.

```bash
npm install
npm run build && npm start
```

Start the complete live development stack from repository root:

```bash
cd ..
./dev.sh
```

Open the printed `http://<LAN-IP>:3000` URL locally or from another device on
the LAN. API requests use that same origin under `/api/*`; Next.js proxies them
to FastAPI on private port 8000. Root launcher also starts/checks ClamAV and
Qdrant, so a run cannot silently begin with required services absent.

`npm run lan` is an alias for root launcher. `npm run dev` remains the
frontend-only mock workflow. Dev settings in `next.config.ts`:

- `upgrade-insecure-requests` in the CSP is gated to production. In dev it would
  force every `_next/static` asset to `https` over the LAN, and the page would
  load unstyled (`localhost` is exempt, so it only bites over the network).
- `allowedDevOrigins` is auto-populated from this machine's network interfaces,
  so fast-refresh works over the LAN and a changed IP needs no edit.
- `CLANNON_DEV_BACKEND_URL` enables `/api/*` reverse proxying. Root launcher
  owns this server-only variable; production continues using its direct API URL.

## Configuration map — everything changeable, and where

Three config files plus `.env.local`. If you need to change something
later, it is in one of these — components never hardcode any of it.

| File | What it controls |
|---|---|
| **`src/config/app.config.ts`** | API mode (mock/http), backend base URL, **every endpoint path** (config sync, auth, OAuth start, runs, run stream, memory, usage, model settings), request timeout/credentials, feature flags (billing UI, demo entry), behavior limits (minimum brief length). |
| **`src/config/site.config.ts`** | Product name (wordmark, titles, metadata, legal text), tagline, description, site URL, support/privacy/legal contact emails, **sign-in providers** (password/Google/GitHub/Apple — reorder or remove to change the auth pages), password minimum length, footer credit lines, legal entity name, effective dates, governing law, minimum age, deletion window, refund window/ceiling, the subprocessor list disclosed in the privacy policy. |
| **`src/config/theme.config.ts`** | **Every color in both themes.** Tokens are injected as CSS variables by the root layout; `globals.css` never hardcodes a color. Change the palette here without touching CSS. (Fonts are build-time: swap them in `src/app/layout.tsx`, one import.) |
| **`src/config/nav.config.ts`** | Navigation structure: marketing header/footer links and the workspace sidebar/bottom-bar items (labels, routes, icons, order). |
| **`src/config/plans.ts`** | Plan names, prices, token budgets, feature bullets, memory-tier gating, which plan is highlighted. Used by the pricing page, billing settings, memory tier locks, and the sidebar plan chip. |
| **`src/config/demo.config.ts`** | The canned briefs offered by the no-signup landing demo, the report preview length, and the example chips under the workspace composer. The demo always runs the bundled simulator (never the real backend); hide the whole section via `features.demo` in app.config.ts. |
| **`.env.local`** | Per-environment overrides: `NEXT_PUBLIC_API_MODE`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SITE_URL`, contact email overrides. See `.env.example`. |

Things that are *content*, not config: marketing page copy lives in
`src/components/marketing/`, legal document text in `src/app/legal/`
(both interpolate names/emails/dates from `site.config.ts`, so a brand
or contact change never requires touching them).

### Backend → frontend sync (read-only)

In http mode the frontend GETs the backend's public **`/config`**
endpoint once per session (`RemoteConfig` in `src/lib/api/types.ts`).
Whatever the backend includes — plans, feature flags, limits —
**overrides the local config files**, so pricing or budgets changed on
the backend appear in the UI without a frontend deploy. Consumers use
`useEffectivePlans()` / `useEffectivePlan()` instead of importing
`PLANS` directly.

The channel is strictly one-way: the frontend has **no write path** to
system configuration. The only writes a signed-in user can make are to
their own scoped data (their runs, their wiki, their per-layer model
choice), each through its own authenticated endpoint — and the backend
remains the enforcing authority for every limit regardless of what the
UI displays. If `/config` is missing or unreachable, local defaults
apply and nothing breaks.

### Switching to the real backend

```bash
# .env.local
NEXT_PUBLIC_API_MODE=http
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com
```

That's it. If a backend route is named differently, edit the
`endpoints` table in `app.config.ts` — `:id` and `:provider` segments
are substituted automatically.

A reference implementation of this contract — wrapping the real
Vraksha pipeline with live SSE decision-log streaming, cookie auth,
and SQLite-backed wiki memory — lives at `backend/api/` (FastAPI).
Run both sides together:

```bash
# from repository root
./dev.sh
```

### The contract the backend must serve

`src/lib/api/types.ts` mirrors the Flow pipeline schemas. The http
client (`src/lib/api/http.ts`) expects:

| Endpoint | Method | Returns |
|---|---|---|
| `/config` | GET (public) | `RemoteConfig` — plans/features/limits the UI should display (read-only sync; optional, 404 falls back to local config) |
| `/auth/login` `/auth/signup` | POST | `User` (sets httpOnly session cookie) |
| `/auth/oauth/:provider` | GET (navigation) | Runs the OAuth handshake, redirects back to `/app` with the session cookie set |
| `/auth/me` | GET | `User` or 401 |
| `/auth/logout` | POST | 204 |
| `/runs` | GET / POST | `RunSummary[]` / `{id}` |
| `/runs/:id` | GET | `Run` |
| `/runs/:id/stream` | GET (SSE) | `data:` lines, each one JSON `RunEvent` |
| `/memory` | GET / POST | `MemoryEntry[]` / `MemoryEntry` |
| `/memory/:id` | PUT / DELETE | `MemoryEntry` / 204 |
| `/usage` | GET | `UsageSummary` |
| `/settings/models` | GET / PUT | `LayerModelConfig[]` / 204 |

`RunEvent` is a tagged union: `status`, `log` (a `DecisionLogEntry`),
`expert`, `sources`, `report_delta`, `report_done`, `usage`. The mock
client (`src/lib/api/mock.ts`) is a reference implementation of the
exact semantics.

## Architecture

```
src/
  config/
    app.config.ts    ← API mode, backend base URL, all endpoint paths, limits
    site.config.ts   ← brand, contacts, auth providers, legal values
    theme.config.ts  ← every color token, both themes
    nav.config.ts    ← marketing + workspace navigation structure
    plans.ts         ← pricing/plan single source of truth
    demo.config.ts   ← canned briefs for the no-signup landing demo
  lib/api/
    types.ts         ← Flow contract mirrors
    client.ts        ← ClannonClient interface
    http.ts          ← real backend adapter (fetch + SSE)
    mock.ts          ← in-browser pipeline simulator (default)
    hooks.ts         ← TanStack Query hooks + useLiveRun stream folding
  components/
    ui/              ← primitives (button, input, dialog, tabs…)
    brand/           ← logo (tree-ring mark)
    marketing/       ← landing page sections
    app/             ← workspace (decision log, experts, report…)
  app/
    page.tsx         ← landing
    (auth)/          ← login, signup, forgot-password (incl. OAuth buttons)
    legal/           ← privacy, terms, acceptable-use, refunds
    app/             ← workspace (dark), guarded by RequireAuth
```

Design system: tokens in `src/app/globals.css` ("Botanical Archive" —
warm paper/ink light theme, green-ink dark theme; amber is reserved
for memory). Fonts: Fraunces / Schibsted Grotesk / Spline Sans Mono,
self-hosted via `next/font`.

Frontend quality is scored by `benchmark/PAID_PRODUCT_BENCHMARK.md`: whether product
experience justifies a hundreds-per-month price through value, speed, trust,
workflow completeness, recovery, and repeat use. Screenshot beauty scores are
supporting evidence only. Current baseline and work order live in
`reports/frontend/frontend_report_v5.md`.

Theming: light/dark/system, toggleable from every shell (marketing
header, auth pages, workspace sidebar and mobile bar). State lives in
`localStorage["clannon.theme"]`; `public/theme.js` applies the class
before first paint (no flash, no inline script), and
`src/components/theme.tsx` (`useTheme`/`ThemeToggle`) keeps it in sync,
following the OS preference when set to system.

## Security posture

- CSP + full security-header set in `next.config.ts` (frame-ancestors
  'none', nosniff, strict referrer, HSTS). `connect-src` is limited to
  the configured backend origin.
- No `dangerouslySetInnerHTML` anywhere. Reports render through
  react-markdown **without** raw-HTML support; images are stripped,
  URL protocols sanitized.
- Auth expects httpOnly cookies from the backend — tokens are never
  stored in JS-accessible storage. (The mock's localStorage session is
  mock-only and clearly marked.)
- All form input validated with zod before submission; the password
  reset flow never reveals whether an account exists.
- `NEXT_PUBLIC_*` only carries public values; secrets have no place in
  this app.
