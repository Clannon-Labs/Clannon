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
