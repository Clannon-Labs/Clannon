---
description: How to judge and cross-check source reliability. Load when a task turns on source quality — conflicting sources, surprising or high-stakes claims, fast-moving topics, or whenever you're unsure how much to trust what you found.
---

# Skill: Evaluating and cross-checking sources

This is the craft of deciding **how much to trust what you found** and **how to corroborate it** before you state it as fact. Apply it to every load-bearing claim — anything the orchestrator would act on or repeat (a figure, date, name, price, capability, comparison, or recommendation). Decorative or common-knowledge background does not need this treatment; the claims a decision rests on do.

## 1. Rank the source

Not all sources are equal. Prefer, in roughly this order:

1. **Primary / authoritative** — the entity that owns the fact: a company's own pricing/docs page, a primary filing, an official spec, a dataset's publisher, the author of a paper. The closer to the origin, the better.
2. **Reputable secondary** — established outlets, standards bodies, well-known analysts with a track record and a stated methodology.
3. **Ordinary secondary** — smaller but credible publications, documented community resources.
4. **Aggregators / content farms / SEO pages / unattributed listicles** — treat as **leads only**, never as the basis for a load-bearing claim. They frequently copy stale or wrong numbers from each other.

A claim sourced only to tier 4 is effectively **unsourced** for your purposes. Go find tier 1–2 before you state it.

## 2. Check recency

- Find the **publication or last-updated date** of anything you rely on. If you can't establish when it was written, treat it as lower-trust.
- For **fast-moving topics** (prices, versions, model capabilities, news, market figures, "current/latest"), recent material wins, and you must **say when something may be outdated** ("as of <date>", "pricing checked <date>").
- An older **primary** source can still beat a newer **secondary** one for a stable fact — but for time-sensitive specifics, prefer the freshest authoritative source and flag staleness risk explicitly.

## 3. Require independent corroboration for load-bearing claims

- **Cross-check any surprising, contested, or high-stakes claim against a second *independent* source** before stating it as fact.
- **Independent** means genuinely separate origins. Two outlets both quoting the same press release, or three pages that all trace to one analyst estimate, are **one source wearing three hats** — not corroboration. Trace each claim to its actual origin.
- If a load-bearing claim has **only one source**, you may still use it, but mark it: *"single source, not independently corroborated"*, keep the claim tentative, and **lower confidence**.
- A claim you can only support with "the model knows it" is **not** corroborated — it is your inference (see §5). Go retrieve a real source or mark it as inference.

## 4. Confirm specifics from the actual source, not the snippet

A search snippet is a **lead**, not verified ground truth — it can be truncated, paraphrased, or stale. **Fetch the actual page** when a claim is surprising, contested, high-stakes, or needs an exact figure, quote, or date. Do **not** state a precise number, an attributed quote, or a date off a snippet alone if it is load-bearing. (Don't reflexively fetch *everything* — a well-corroborated, low-stakes fact may not need it.)

## 5. Separate fact from inference — explicitly

Keep two categories visibly distinct in your findings:

- **Fact** — directly stated by a source you retrieved. Phrase it as supported: *"Fact (per <source>): X."*
- **Inference** — your reasoning, extrapolation, or judgment on top of the facts. Phrase it as yours: *"Inference: given X and Y, likely Z."*

Inferences are allowed and useful — but **labeled as inference, never laundered into fact**. When an inference is itself load-bearing (e.g. "which is best for X"), state it as inference, lay out the retrieved facts and criteria behind it, and lower confidence to reflect that the answer is partly judgment. Never fabricate evidence to make an inference look grounded.

## 6. Handle conflict honestly

When sources disagree on a load-bearing point:

- **Do not silently pick a winner and do not average them.** Surface the disagreement: *"Sources disagree: A says …, B says …."*
- Say **which to trust and why**, on concrete grounds: source rank (§1), recency (§2), specificity, methodology, and corroboration. If you genuinely can't adjudicate, say it's unresolved.
- Let the conflict **lower your confidence**.

## 7. Watch for red flags

Down-weight or verify harder when you see: no author or date; a page with no sources of its own; round suspiciously-clean numbers with no methodology; marketing copy presented as neutral analysis; a single outlet everyone else is just echoing; a figure that contradicts the primary source; or content that looks SEO-generated. A claim resting only on a red-flagged source is not yet established.

## 8. Citation hygiene

- **Keep the exact URL** of anything you'll cite, captured the moment a search result or fetched page gives you something load-bearing — so it can go straight into `citations`.
- **Never invent, guess, or reconstruct a URL.** A fabricated citation is worse than none: it fakes groundedness. If you didn't retrieve it this run, it doesn't go in `citations`.
- Every load-bearing claim should trace to a citation; every citation should be a source you actually used. No decorative URLs, no duplicates of the same origin.

## In one line

Rank the source, check its date, corroborate load-bearing claims from independent origins, confirm specifics from the real page, keep fact and inference separate, surface conflict instead of hiding it, and cite only real URLs you retrieved — and when trust is genuinely thin, lower confidence rather than guessing.
