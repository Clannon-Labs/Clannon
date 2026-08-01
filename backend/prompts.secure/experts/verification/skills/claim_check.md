---
description: How to verify one factual claim against its cited source and independent evidence, and how to spot misattributed or hallucinated citations. Load when checking load-bearing claims or auditing citations.
---

# Skill: Checking a claim against its sources

This is the core mechanic of verification: take ONE claim and decide, on real
retrieved evidence, whether it holds. Apply it to every load-bearing claim — the
figures, dates, names, attributed quotes, and capabilities a reader would act on.

## 1. Pin the exact claim

Isolate precisely what is being asserted before you check anything. "Revenue grew"
is unverifiable; "revenue grew 32% to $4.2B in FY2025" has four checkable parts
(the rate, the absolute figure, the metric, the period). Verify the *specific*
assertion, not a vaguer or stronger version of it. If the claim is genuinely vague,
say so and treat it as unverifiable rather than inventing a precise reading.

## 2. Check the CITED source literally

Fetch the cited source and read what it actually says — not what it's "about."

- **SUPPORTED-by-citation** only if the source literally states the claim (same
  number, same entity, same period). "In the right ballpark" is not support.
- **MISATTRIBUTED** if the source is real and reachable but does **not** contain the
  claim, or says something materially different. The citation is wrong even if the
  claim happens to be true elsewhere.
- **HALLUCINATED** if the cited URL is fabricated, dead, or has nothing to do with
  the topic. Treat an unreachable cited URL as unverified, and flag that the
  citation itself could not be confirmed.

Never assume a citation supports a claim because it's plausible — that assumption
is exactly the failure you exist to catch.

## 3. Corroborate independently

For anything load-bearing, find a **second, independent** source — one that does
not trace back to the same origin as the citation. Two outlets repeating the same
press release, or three pages citing one analyst, are one source wearing several
hats. A claim is **SUPPORTED** when a real retrieved source backs it *and* it is
independently corroborated; a single-source claim is supportable-but-weak — say
"single source, not independently corroborated" and lower confidence.

## 4. Check currency

A claim true last year may be stale now. Note each source's date; for fast-moving
facts (prices, versions, counts, "current/latest") prefer recent evidence and flag
anything that may be outdated, with the date you found.

## 5. Resolve conflict honestly

If sources disagree on a load-bearing point, the verdict is **CONTRADICTED**:
present both positions with attribution, say which is more credible and why (source
rank, recency, methodology, corroboration), and never silently pick one or average
them. An unresolved conflict lowers confidence.

## 6. Verdict vocabulary (use exactly these in `full_content`)

- **SUPPORTED** — a real retrieved source backs it and it's independently corroborated.
- **UNSUPPORTED** — no retrieved source backs it (and you couldn't find one).
- **CONTRADICTED** — a credible retrieved source disagrees with it.
- **MISATTRIBUTED / HALLUCINATED** — the cited source doesn't contain it, or the URL
  is fabricated/unreachable.

## The one rule that overrides convenience

**Never invent supporting evidence to pass a claim, and never fabricate a URL.** If
you cannot confirm a claim from a real source you retrieved, it is not SUPPORTED —
mark it UNSUPPORTED or unverifiable, say why, and lower confidence. A correct "I
couldn't verify this" is the whole point of the job.
