# Private-alpha security campaign — final report card

- **Campaign window:** 2026-08-10 to 2026-08-11
- **Product checkpoint:** `d0a333e`
- **Final decision:** **STOP — do not invite private-alpha testers yet**
**Why:** substantial remediation landed and passed independent retest, but two
frontend launch blockers remain and deployment/broad threat-model coverage is
incomplete.

This is the unified, frozen campaign record: destination, changes, evidence,
hurdles, and remaining work. Live priorities still belong in `docs/ROADMAP.md`.
Detailed auditor evidence remains in `reports/{backend-audit,frontend-audit}/`.

## Cold-read story

Clannon was approaching private alpha on a real domain. Owner wanted assurance from
senior adversarial researchers who would look for exploitable design decisions,
control bypasses, unsafe compositions, and working-under-normal-conditions failures;
static analysis alone was explicitly insufficient.

We created two independent, source-read-only roles: one for backend/root and one for
frontend/browser. They threat-modeled reachable attacker paths, measured behavior,
and wrote findings. They could not edit code or close their own findings. Owning
implementation agents fixed validated problems; coordinator reviewed, tested,
committed, and pushed; auditors then retested exact revisions independently.

Campaign tracked four backend launch-control findings and five frontend findings,
with one waitlist-timing issue shared across both views. All four backend launch
controls and two frontend findings were independently mitigated. Browser regression
coverage was repaired, and a targeted backend identity/tenant audit found no
validated current-scope defect. Two frontend blockers remain, broad security families
and real deployment remain partially or wholly untested, so final decision is STOP.

Owner then ended autonomous iteration. Every active run finished naturally; no audit
or remediation session remains active. Next work happens only as owner-requested,
bounded steps.

## Executive scorecard

| Area | Result | Meaning |
|---|---|---|
| Independent audit capability | **BUILT** | Separate backend and frontend adversarial auditors run with source and Git read-only. |
| Backend launch controls | **4/4 MITIGATED** | Production mode/YARA, mail readiness, outbound mutation, and waitlist timing independently retested. |
| Frontend baseline findings | **2 MITIGATED / 2 BLOCKERS OPEN / 1 LOW RESIDUAL** | PDF isolation and waitlist timing closed; production mock mode and URL admission remain blockers; CSP remains defense-in-depth debt. |
| Backend identity/tenant isolation | **TARGETED PASS, PARTIAL COVERAGE** | No current-scope defect survived 99 focused tests plus 110 auditor probes; important race/deployment cases remain untested. |
| Browser regression harness | **REPAIRED** | Default private-alpha Playwright run: 15 passed, 1 environment-gated skip. |
| Real deployment assurance | **NOT PROVEN** | Railway topology, proxy behavior, real mail/providers, live Qdrant, and production accounts were not exercised. |
| Whole-system security verdict | **NO PASS** | Campaign ended with evidence-backed STOP, not an inflated green verdict. |

## Destination we started with

Goal: decide whether Clannon was safe enough for a real-domain private alpha, using
independent auditors that think like attackers—not only static analyzers. Required
end state:

1. make production mode, YARA, and mail readiness fail closed;
2. make owner-disabled outbound mutations unreachable below model reasoning;
3. independently retest every remediation;
4. measure and remove waitlist membership timing leakage;
5. exercise production-like frontend/backend paths and publish honest GO or STOP;
6. preserve deferred surfaces instead of silently treating untested as safe.

## What was fixed

| Original risk | Remediation shipped | Independent result |
|---|---|---|
| Canonical `CLANNON_ENV=production` did not govern every strict control; contradictory modes were accepted. | One canonical runtime-environment authority now drives strict config, YARA, and mail selection; invalid/contradictory modes fail. | Backend-audit F-01: **RETESTED — MITIGATED**. |
| Production could start before validating mail configuration. | FastAPI lifespan now preflights production mail before readiness. | Backend-audit F-02: **RETESTED — MITIGATED**. |
| Direct HTTP/notifier mutation remained discoverable and callable despite private-alpha policy. | Mutating capability keys are omitted from discovery, rejected on direct lookup, and removed from model prompts. | Backend-audit F-03: **RETESTED — MITIGATED**. |
| Waitlist responses exposed account state through provider-mail latency. | Mail work starts only after ASGI response-body emission. | Backend-audit F-04 and frontend-audit F-04: **RETESTED — MITIGATED** at ASGI boundary. |
| Frontend could silently fall back to mock authentication. | Unset mode now selects HTTP, invalid values fail builds, CI is explicit, and mock UI is visibly marked. | Original silent fail-open fixed; explicit production `mock` remains open. |
| Backend-supplied source URLs could reach clickable sinks without a server policy. | Shared API projection now rejects non-HTTP(S), credentials, malformed escapes/hosts/ports, controls, and relative URLs before REST/SSE/persistence output. | Backend half mitigated; narrower frontend admission gap remains open. |
| PDF preview relied on an unsandboxed same-origin iframe conflicting with CSP. | PDF opens as a top-level `blob:` link; product embeds no frame; CSP uses `frame-src 'none'`. | Frontend-audit F-03: **RETESTED — MITIGATED**. |
| Waitlist-gated signup broke browser authentication tests, hiding real regressions. | Shared mock-UI authentication helper keeps `/signup` gated; real-backend tests are explicit opt-in. | Typecheck/lint clean, Vitest **258/258**, Playwright **15 passed + 1 gated skip**. |

Primary remediation commits: `0ec15dd`, `934b138`, `379bdfb`, `dc2cd8e`, and
`4a013c4`. Independent retest evidence was recorded before clean stop `d0a333e`.

## What remains

### Must fix before private-alpha GO

1. **Production mock build — OPEN.** `NEXT_PUBLIC_API_MODE=mock` still builds under
   `NODE_ENV=production` and permits local mock login. Production must reject it while
   preserving deliberate development/test use.
2. **Frontend source URL admission — OPEN.** Browser policy blocks dangerous schemes
   but still accepts credential-bearing URLs and parser-tolerated malformed percent
   escapes. Server output rejects both, but frontend trust boundaries must defend
   independently.

### Known residual, not current launch blocker

- **CSP `script-src 'unsafe-inline'` — OPEN, low residual.** No reachable attacker-
  controlled inline-script sink was found. Removal requires a tested Next.js
  rendering/nonce or SRI migration; changing only header would break product.
- Missing YARA rules fail on first universal scan, not at application startup.
- Eleven Dependabot alerts remained at stop: nine in isolated audit tooling and two
  frontend development-chain alerts. Reachability was not established, so neither
  “exploitable” nor “dependency-clean” is claimed.

### Deferred security coverage

- session/logout/token races and already-open SSE after revocation or expiry;
- multi-process, restart, replica, limiter/send, and persistence lifecycle races;
- live Qdrant plus real mail, billing, model providers, accounts, and data;
- deployed Railway variables, workers, volumes, proxy/TLS behavior, egress, and timing;
- deeper SSRF/DNS/redirect/resource-exhaustion paths;
- uploads, archives, parsers, artifacts, workspaces, path/symlink handling;
- execution sandboxing when execution is enabled;
- agentic re-entry, availability/economic abuse, secrets/observability, and broader
  supply-chain/image/SBOM review.

These are not known vulnerabilities. They are uncompleted assurance work and prevent
a whole-system PASS.

## Backend access-control result

Targeted FastAPI review found no validated current-scope cross-user authorization or
tenant-isolation defect.

- exact revision: `dc2cd8e9f2c7f82bbce4d55ae8fa40c430a39c48`;
- focused suite: **99 passed, 3 skipped** because live Qdrant was unavailable;
- independent auditor probe: **110 passed, 0 failed**;
- route registration collision check: none found;
- artifact adapter is namespace-only, not independently tenant-aware. Corrupting
  trusted run metadata in an auditor-only probe crossed namespaces, but no client-
  writable path to corrupt that metadata was found. Recorded as defense-in-depth
  seam, not a validated vulnerability.

Verdict: good bounded evidence, not proof against deferred races or deployed topology.

## Campaign evolution

| Stage | What happened | Outcome |
|---|---|---|
| 1. Build independent audit lane | Backend/root and frontend auditors received adversarial charters, durable outputs, research/scanner capability, and enforced read-only source/Git sandboxes. | Auditors could investigate and report but could not self-fix or self-close findings. |
| 2. Baseline attack-path audits | Auditors reviewed working-as-designed bypasses, configuration composition, browser sinks, and launch paths—not only scanner matches. | Backend found four launch-control problems; frontend found five tracked issues. Verdict became STOP. |
| 3. Remediation | Owning backend/API/security/frontend lanes implemented fixes. Coordinator reviewed, tested, committed, and pushed them. | Major backend controls and two frontend findings closed. |
| 4. Independent retest | Auditors re-read exact revisions and measured failure branches, browser behavior, and ASGI ordering. | Backend F-01–F-04 and frontend F-03/F-04 independently mitigated. |
| 5. Deeper bounded proof | Backend auditor exercised authorization/tenant relationships across routes and stores. Frontend browser harness was repaired and rerun. | No current-scope backend access-control defect; browser suite useful again. |
| 6. Natural clean stop | Owner ended autonomous iteration after active runs completed. No new work dispatched. | Two frontend blockers and broad/deployment coverage preserved as open. Final verdict: STOP. |

## Hurdles encountered

- Claude and later Codex worker quotas were exhausted during parts of campaign.
- Codex Security deep-scan preset required six discovery workers; runtime exposed
  three. We used honest targeted sequential review and did not label it a deep scan.
- Concurrent suites contaminated shared environment; coordinator reran proofs cleanly.
- Stale `.next` data contained old-profile paths and caused Turbopack permission
  errors. Fresh-cache rerun separated harness contamination from product behavior.
- Waitlist gating invalidated old open-signup E2E assumptions; harness needed repair
  before browser results were trustworthy.
- Shared HEAD advanced during audit. Exact-SHA archives/diffs kept evidence tied to
  reviewed code.
- Audit reports and proposals are intentionally local/gitignored. This tracked card
  preserves campaign conclusion across profiles without publishing exploit detail.

## Final judgement

Campaign did much more than identify problems: it built independent audit machinery,
fixed substantial launch controls, repaired regression coverage, and independently
verified mitigations. Security posture improved materially.

Still, private alpha remains **STOP**. Close two frontend blockers, rerun frontend
audit, then perform a bounded deployment-readiness pass. Only evidence from those
steps can change verdict to GO.

## Detailed evidence, if needed

- `reports/backend-audit/report_v1.md` — launch-control baseline findings.
- `reports/backend-audit/report_v2.md` — independent remediation retest.
- `reports/backend-audit/report_v3.md` — targeted FastAPI access-control review.
- `reports/frontend-audit/report_v1.md` — frontend baseline findings.
- `reports/frontend-audit/report_v2.md` — frontend remediation retest.
- `proposals/to-owner/2026-08-11_security-campaign-checkpoint.md` — chronological
  local campaign log and clean-stop ruling.
