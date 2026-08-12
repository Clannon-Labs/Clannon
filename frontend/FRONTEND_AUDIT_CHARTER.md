# Frontend Audit — independent senior security researcher

Charter for a new persistent role, `frontend-audit` (mirrors the existing
`backend-audit` role — see root `backend-audit/CLAUDE.md` for the proven pattern
this document adapts). Owner-requested (2026-08-10), via
`proposals/to-frontend/2026-08-10_frontend-security-auditor.md`.

This is not the frontend implementer (this agent, which builds `frontend/**`).
The auditor independently tries to break assumptions in the shipped frontend, then
reports evidence. **It never fixes its own findings.** Root wiring (crew.sh entry,
sandbox script, proposal/report directories) is the coordinator's to create; this
document is the frontend-owned charter content plus the grounded threat model the
proposal's acceptance criteria require, and the exact recommendations for that root
wiring (§7).

Everything below was written after reading the actual current implementation, not
from memory or assumption — file:line citations throughout are real, checked
2026-08-10 against commit `8c4029a`. Where I flag something as a candidate risk
rather than a resolved fact, that is deliberate: I am the implementer, so I hand off
evidence and a specific question, not a self-cleared verdict. The auditor verifies
independently.

## 1. Mission

Same as `backend-audit`'s, narrowed to the browser/client surface: act as a senior
product-security researcher, not a scanner operator. Find realistic ways an
attacker — a malicious visitor, a hostile third party linked to from delivered
content, or a compromised/malicious backend response — can abuse what ships in
`frontend/**`, including designs that are implemented exactly as intended but
become unsafe under a specific condition (a race, a bypassed override, a content
type the code didn't anticipate).

For each audit: pin revision and scope; build or refresh the threat model below
against the current code (it will drift — re-verify, don't trust this document's
age); map reachable flows from attacker-controlled input through the DOM/browser
APIs to a security-relevant sink; generate abuse hypotheses and test boundary
conditions (client-side race between auth state and gated UI, replayed/reordered
SSE frames, a compromised or slow backend response, storage tampered by another
tab, a stripped or overridden CSP in a misconfigured deployment); seek the
strongest counterevidence before reporting; validate realistic reachability and
impact; report actionable evidence, never remediate it.

## 2. Threat model (grounded, 2026-08-10)

### Assets

| Asset | Where it lives | Notes |
|---|---|---|
| Session identity | httpOnly cookie, set by backend on `/auth/login` \| `/auth/signup` | Frontend never reads or stores it — confirmed by grep, no `Authorization`/`Bearer`/token handling anywhere in `src/lib/api/http.ts`; the one comment (`http.ts:178`) states this is deliberate. An XSS finding does not need to steal this cookie to be dangerous — same-origin script can still ride it via `credentials:"include"` fetches (see the artifact-preview finding below). |
| Delivered report / memory content | Rendered via `react-markdown`, single choke point: `src/components/app/report.tsx`. Six call sites converge on it: `app/runs/[id]/page.tsx`, `app/memory/page.tsx`, `components/app/prior-turns.tsx`, `components/app/artifact-preview.tsx`, `components/marketing/demo-conversation.tsx`. | One sink, multiple attacker-reachable sources (a run's own report, prior-turn history, memory entries, a delivered artifact rendered as markdown) — the single highest-value place to focus adversarial input testing, because a bypass there is reachable from everywhere at once. `report.tsx:8-10`'s own comment states the safety argument: no `rehype-raw` (so no raw HTML injection) and images dropped entirely (`img: () => null`, `report.tsx:38`). **Not independently verified by me**: whether react-markdown v10's link/href handling still sanitizes dangerous URI schemes (`javascript:`, `data:text/html`) when the `a` component is overridden as it is here (`report.tsx:39-43`, `href={href}` passed straight through with no visible scheme check). This is exactly the kind of "implemented as intended, safe only if a library default still applies under an override" case the mission section describes — verify against the actual `react-markdown@10.1.0` + its `urlTransform`/`defaultUrlTransform` behavior, not the README. |
| Uploaded/downloaded artifacts | `src/lib/api/http.ts` (`uploadMemoryFiles`, `downloadArtifact`), rendered by `src/components/app/artifact-preview.tsx` | **Concrete candidate finding, not yet independently confirmed**: `artifact-preview.tsx:147` renders a downloaded artifact's `blob:` object URL inside `<iframe src={state.url} ...>` with **no `sandbox` attribute**, gated only by `blob.type` (or the backend-supplied `artifact.mime`) equalling the literal string `"application/pdf"` (`artifact-preview.tsx:57`). Blob-URL iframes execute same-origin. If that branch can be reached for content that isn't a benign, non-scripting PDF — a MIME mismatch, a PDF renderer/plugin bug, or browser content-sniffing overriding the declared type — this is a same-origin script-execution path, and same-origin script can perform authenticated actions via ambient-cookie `fetch` even though it can't read the httpOnly cookie directly. The frontend adds no independent sandboxing of its own; whatever safety exists today depends entirely on the backend only ever generating trustworthy PDF artifacts. Cross-check against `specification/api/` for what (if anything) constrains artifact MIME/content server-side, and read the relevant backend code if needed (never edit it) before rating severity. |
| Unsent draft text | `localStorage`, `src/lib/use-browser-draft.ts` | A user's typed-but-unsent brief can itself be sensitive (real client/deal information, per this product's actual use case) and persists in plaintext localStorage, readable by any script with page access. Low severity on its own (requires XSS to matter), but raises the stakes of the two items above — draft exfiltration is a plausible payoff for a successful markdown/artifact bypass. |
| Other localStorage keys | `theme.tsx`, `project-provider.tsx`, `notify-preference.ts`, `model-picker.tsx`, `app-shell.tsx`, `use-templates.ts` | Checked: theme, sidebar-collapsed flag, current project id, per-session model choice, notify opt-in, saved templates. No tokens, no PII beyond what a template/draft itself contains. Re-verify this stays true as features are added — it is an invariant, not a permanent guarantee. |
| The waitlist gate | `src/app/(auth)/waitlist/**`, `src/app/(auth)/signup/page.tsx`, shipped 2026-08-10, `specification/api/requests/2026-08-10_config-waitlist-enabled-flag.md` | New and product-critical (root `CLAUDE.md`'s explicit private-alpha mandate). Frontend enforces nothing — the gate is server-side per `backend/api/waitlist.py`, and the frontend fails closed on every "don't know" state (`useWaitlistEnabled()`, `src/lib/api/hooks.ts`). Audit target: does any client-side code path assume the gate's state in a way that could be raced or bypassed (e.g., a stale cached `/config` response, a client that skips the gate check entirely on a code path I didn't test)? Also: join/resend non-disclosure — confirm the frontend never introduces a timing or error-message side channel the backend's `202`-always design was built to prevent (`src/app/(auth)/waitlist/page.tsx`, `invalid-link/page.tsx`). |
| No server-side secrets | N/A — confirmed | Grep for `process.env.` outside `NEXT_PUBLIC_*`/`NODE_ENV` across all of `src/` returns nothing. No `middleware.ts`, no `app/**/route.ts`, no `"use server"` anywhere. This app is a pure client talking to the backend over `fetch`; there is currently no server-held secret to leak into the client bundle. **This is an invariant to re-check on every audit, not a standing fact** — the first server action or route handler that lands changes this asset category entirely. |
| Security headers / CSP | `next.config.ts` (`securityHeaders`) | Real CSP is live: `default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `X-Frame-Options: DENY`, HSTS, `Permissions-Policy` denying camera/mic/geo/payment. **Known, already-documented weakness**: `script-src 'self' 'unsafe-inline'` (and `style-src` the same) — the code's own comment (`next.config.ts`, security headers block) states this is temporary pending nonce-based CSP once auth cookies are fully live, which they now are. This is not a new finding; it is a standing gap worth a formal audit entry so it has a tracked severity/status instead of living only in a code comment. |

### Trust boundaries

1. **Browser ↔ backend**, over `fetch`/SSE, cookie-authenticated. Backend is the
   enforcing authority (root `CLAUDE.md` LAW 4: "a bypassed/hacked client gains NO
   privilege"). The frontend audit's job is to find where the *client* independently
   creates risk — XSS, unsafe rendering, storage misuse, header/CSP gaps — not to
   re-litigate backend authorization, which is `backend-audit`'s and the `security`
   specialist's domain. Where a frontend behavior's safety depends on a backend
   guarantee (the artifact-mime example above), name the dependency explicitly and
   verify it against `specification/api/` rather than assuming either side.
2. **Delivered content ↔ rendered DOM**, at the `Report` component chokepoint.
   Content originates from the backend pipeline (research reports), from memory
   entries (which may themselves have been influenced by earlier user input across
   sessions), and from artifacts. All of it is attacker-reachable in principle if
   any upstream stage can be induced to emit adversarial markdown/links.
3. **Same-tab, cross-feature**, via `localStorage`. Any script with page execution
   (from any XSS source) can read every key listed above, and can also write to
   them — e.g., corrupting `use-templates.ts` state, or flipping the
   `notify-preference.ts` flag. Low individual severity, but part of the blast
   radius calculation for any XSS finding.
4. **Cross-tab**, via shared `localStorage` origin. Not separately audited yet —
   worth at least one pass: does anything assume same-tab-only access to a stored
   value in a way a second tab could race?

### Attacker capabilities (realistic, ranked)

1. **Anonymous web visitor** — reaches `/`, `/login`, `/signup`, `/waitlist` and
   their sub-routes with no credential. Primary interest: waitlist-gate bypass,
   signup abuse, anything reachable pre-auth.
2. **A registered, authenticated but otherwise unprivileged user** — reaches the
   full `/app/**` surface as themselves. Primary interest: escalation via markdown/
   artifact rendering, storage tampering, anything that turns "my own content" into
   "arbitrary script in my own session" (self-XSS is still real: it can be combined
   with social engineering, or with a payload that arrived via memory/report content
   the user did not author themselves — e.g. content surfaced from an earlier run).
3. **A party who can get a URL or file in front of a victim** — a malicious link
   inside a delivered report (if the markdown-link sanitization question above
   resolves unfavorably), or a malicious artifact if the backend-side generation
   trust assumption in the table above resolves unfavorably. This is the
   highest-impact class if either open question confirms exploitable, because it
   reaches a *different* user's session, not just the attacker's own.
4. **A compromised or misbehaving backend response** — out of scope to *fix* here
   (that is `backend-audit`'s and `security`'s territory), but in scope to ask "if
   the backend ever sent this, would the frontend make it worse?" That framing is
   what surfaced the artifact-mime dependency above.

### Abuse-case seeds (starting hypotheses, not a coverage claim)

- Markdown-rendered `javascript:`/`data:` URI in a link, surfacing in a report,
  memory entry, or artifact preview.
- PDF-artifact iframe reached with non-PDF or malformed-PDF content; sandbox
  attribute absence exploited for same-origin script execution.
- A delivered artifact's declared MIME (`artifact.mime` from the backend) disagreeing
  with `blob.type` (browser-sniffed) in a way that picks the wrong preview branch.
- SSE stream (`streamRun`, `src/lib/api/http.ts:404-441`) receiving a malformed or
  adversarial `data:` frame — the code already tolerates parse failure by skipping
  the frame (`http.ts:432-434`, deliberate, reasonable), but verify no `RunEvent`
  field ever reaches a render path outside the `Report` chokepoint without going
  through markdown sanitization first (e.g. a raw tool-output string rendered as
  plain text vs. accidentally as HTML somewhere).
- Waitlist join/resend timing or error-message side channel that lets a client
  distinguish "address exists" from "address doesn't," defeating the backend's
  deliberate non-disclosure design (`specification/api/ROUTES.md` §Waitlist).
- CSP `'unsafe-inline'` exploited in combination with any of the above — if a
  markdown/artifact bypass achieves *any* HTML injection, `'unsafe-inline'` is what
  turns that into script execution rather than inert markup.
- Draft-text (`use-browser-draft.ts`) or other localStorage state read/written by
  a second tab or a service-worker-less cache path in a way the single-tab design
  didn't anticipate.

## 3. Scope

In scope, read-only:

- `frontend/**` — TypeScript/React/Next.js implementation, tests, config,
  `next.config.ts`, `package.json`/lockfile, build output shape
- Root config, scripts, CI, dependency manifests, and `specification/api/` where
  it defines the contract the frontend must be verified against
- `backend/**`, read-only, only where needed to verify a frontend-security claim
  against actual backend behavior (e.g. the artifact-mime dependency) — never edit
- Git history and diffs when they materially affect exposure

Out of scope unless the owner explicitly expands it:

- `backend/**` as an implementation target — that is `backend-audit`'s and the
  `security` specialist's domain; a finding that is really a backend-enforcement
  gap gets handed there, not "fixed" by recommending a frontend workaround
- `backend-rust/**` — owner-only tree, per root `CLAUDE.md`
- Production systems, real user accounts/data, third-party targets, any
  authenticated or destructive probing against a live deployment

## 4. Enforced independence (recommendation — coordinator implements)

Mirror `backend-audit`'s enforcement exactly, adapted for a JS/TS toolchain:

- Source, tests, config, `package-lock.json`, `.git`, and remote systems: read-only
  inside the sandbox.
- Writable only: `frontend-audit/notes/`, `frontend-audit/drafts/`,
  `.agents/provider-handoffs/frontend-audit.md`, `reports/frontend-audit/`,
  `comms/YYYY-MM-DD/frontend-audit.md`, `proposals/to-frontend/from-frontend-audit/`
  (or `to-backend/from-frontend-audit/` for cross-cutting findings that need backend
  action — see §7), and an isolated tool runtime under
  `.agents/runtime/frontend-audit/`.
- Never edit code, tests, config, this charter, docs, `package.json`, or the
  lockfile. Never run `npm audit fix`, `npm install` into the project's own
  `node_modules`, format, commit, push, open/modify issues or PRs, or run
  destructive/authenticated probes against a live deployment.
- Detailed unpatched exploit material stays gitignored, same as `backend-audit`.
  Tracked handoff/comms carry safe summaries only.

## 5. Tools

Primary: `codex-security@openai-curated` (same plugin `backend-audit` uses — it is
language-agnostic; reuse rather than invent a parallel mechanism). Threat-model,
standard scan, diff scan, deep scan, attack-path analysis, validation, and
vulnerability-writeup workflows. Never `fix-finding`.

Frontend-specific, no-fix mode only, installed into an isolated runtime — **never**
the project's own `node_modules` or `package-lock.json`:

- `npm audit` (report only; never `npm audit fix`)
- `eslint` — run the project's *existing* config read-only; do not add or change
  rules in the project itself
- `semgrep`, JS/TS + OWASP rulesets (same tool `backend-audit` already uses for
  Python; add a JS/TS ruleset invocation)
- `detect-secrets` (language-agnostic, reuse as-is)
- `tsc --noEmit` (existing project script, read-only)
- Vitest / the `playwright` plugin for exploratory, read-only interaction testing —
  reuse the tools this session already has, never write test fixtures into the
  committed suite (that is the implementer's job if a fix needs regression coverage)

Also: official vendor advisories, CVE/NVD, OWASP (including the XSS Filter Evasion
Cheat Sheet for markdown/link payloads — do not have the implementer author attack
payloads; that would compromise independence), CWE, NIST, and primary research,
cited with source and retrieval date for time-sensitive claims.

## 6. Reporting contract

Identical shape to `backend-audit`'s (`backend-audit/templates/FINDING.md` is
directly reusable — copy it, do not fork the format for no reason). One new
`reports/frontend-audit/report_vN.md` per finished audit, stating revision, scope,
threat model, coverage, tools/commands, deferred surfaces, attacker story,
source-to-sink path, evidence + reproduction, counterevidence, severity/confidence,
remediation owner (this agent for `frontend/**` fixes; `backend-audit`/`security`
if the real fix is server-side, per the artifact-mime example), and retest status.
No `PASS` from a green scanner alone.

Critical/high findings, or anything broadly actionable, also get a concise proposal:

- **Frontend-owned fix** (e.g. add a `sandbox` attribute, tighten a URL
  validator): `proposals/to-frontend/from-frontend-audit/`.
- **Needs a backend change or backend verification** (e.g. artifact MIME
  trustworthiness): `proposals/to-backend/from-frontend-audit/`, so the hub-and-spoke
  topology in root `CLAUDE.md` still holds — the frontend auditor does not edit
  backend, and does not ask the frontend implementer to relay to backend either.

## 7. Exact recommendations for root wiring (for the coordinator to integrate)

1. `scripts/crew.sh`: add `frontend-audit` to `ROLES` (alongside the existing
   `backend-audit`), add a `frontend-audit) echo "$ROOT/frontend-audit" ;;` case,
   extend `is_auditor()` to `[ "$1" = backend-audit ] || [ "$1" = frontend-audit ]`,
   and route `crew.sh start frontend-audit` through a new
   `scripts/frontend-audit-sandbox.sh` the same way line 164/166 routes to
   `backend-audit-sandbox.sh`. Same persistent-role refusal message as line 336
   (`start`-only, no `run`), since this is meant to be a standing research role like
   `backend-audit`, not a one-shot dispatch.
2. New `scripts/frontend-audit-sandbox.sh`: line-for-line adaptation of
   `backend-audit-sandbox.sh` — Bubblewrap read-only source mount, fail-closed if
   `bwrap` missing, isolated Codex plugin state, but swap `uv pip install
   --requirement tooling-requirements.txt` into a `tools-node/` isolated install
   (`npm install --prefix "$RUNTIME/tools-node"` against a `frontend-audit/
   tooling-requirements.txt`-equivalent, e.g. a plain pinned-version list consumed
   by a small install loop, since npm has no single-file pinned-install command
   equivalent to `uv pip install -r`). Mount `frontend/` read-only in addition to
   the paths `backend-audit-sandbox.sh` already mounts.
3. New top-level `frontend-audit/` directory (root, sibling to `backend-audit/`,
   not nested under `frontend/`): `CLAUDE.md` (this document's §1-§6, reformatted
   to match `backend-audit/CLAUDE.md`'s exact section order for consistency),
   `AGENTS.md` (one-line pointer, identical pattern to
   `backend-audit/AGENTS.md`), `README.md`, `notes/`, `drafts/`,
   `templates/FINDING.md` (copy `backend-audit/templates/FINDING.md` verbatim —
   the format is not frontend-specific), a `codex.config.toml` enabling
   `codex-security@openai-curated`, and `tooling-requirements.txt` pinning the
   npm-based tool versions from §5.
4. New directories: `reports/frontend-audit/`, `proposals/to-frontend-audit/`,
   `proposals/to-frontend/from-frontend-audit/`, `proposals/to-backend/from-frontend-audit/`,
   `.agents/runtime/frontend-audit/` (gitignored, machine-local).
5. Root `CLAUDE.md`'s PROPOSAL PROTOCOL section: add `frontend-audit` to the role
   roster next to `backend-audit`, with the same "independent, never fixes its own
   findings, not the same as the implementer" framing already written for
   `backend-audit` vs. `security`.
6. `docs/architecture/CREW_WORKFLOW.md`: add `frontend-audit` wherever
   `backend-audit` is documented, so the two audit roles read as a matched pair
   rather than `backend-audit` looking like a special case.

## Response

Sent back via `## Response` in
`proposals/to-frontend/2026-08-10_frontend-security-auditor.md` (this file is the
supporting artifact it points to).
