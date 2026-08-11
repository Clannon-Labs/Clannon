# Backend audit — launch-control retest complete

Retested report-v1 F-01 through F-04 at exact local `main`
`e34f1f42e528f5662be62a1a42e96ea944ea17a5`; brief prefix `e34f1f4b` does not
resolve. All four are **RETESTED — MITIGATED** within bounded local scope. Focused
proof: 115 passed, 1 unavailable-ClamAV skip plus independent environment, lifespan,
registry/direct-key, native-wrapper, and ASGI body-emission measurements.

No whole-system PASS/GO. Actual Railway/provider behavior and report-v1 deferred
surfaces remain untested. Missing YARA now fails closed on first universal scan but
is not startup-preflighted. Detailed evidence: `reports/backend-audit/report_v2.md`.
Three existing backend proposals have dated retest sections and remain unarchived for
coordinator closure.

## Identity/tenant deep-audit preflight

Coordinator's extreme-priority identity/tenancy/session campaign reached mandatory
Codex Security deep-scan preflight before source analysis. Phase skills, delegation,
and goals passed. Runtime blocked: native-v2 cap 4 gives 3 usable workers; workflow
requires 6 per completed discovery round. No source analysis or finding claim made.
Relaunch with at least 7 total slots (9 recommended), or explicitly authorize
ordinary single-pass fallback. Observed HEAD `dc2cd8e9`; scoped cleanliness remains
unresolved.

## FastAPI access-control report v3 complete

Coordinator-authorized targeted Codex Security fallback completed at exact revision
`dc2cd8e9f2c7f82bbce4d55ae8fa40c430a39c48`. Current-scope result: no validated
cross-user authorization/tenant-isolation defect. Exact-SHA focused suite: 99 passed,
3 live-Qdrant skips. Auditor probe: 110 passed, 0 failed. Route collisions absent.

Coverage is PARTIAL, not whole-system PASS/GO. Deferred: session/token concurrency,
post-revocation open SSE, cross-process/restart/replica lifecycle, limiter/send races,
live Qdrant, deployed topology, providers, and real accounts. Artifact adapter has no
tenant identity; owner-run metadata and current producer binding are authoritative.
No client-writable corrupt-ref path found; no backend proposal opened.

Report: `reports/backend-audit/report_v3.md`. Canonical scan bundle:
`backend-audit/drafts/codex-security-scans/clannon/dc2cd8e9-authz-v3/`.
