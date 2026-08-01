---
description: How to structure a short, action-ready brief. Load when the deliverable is a single focused answer, a recommendation, or a short decision-support write-up where the reader wants the point fast.
---

# Skill: Structuring a brief

A brief exists to let a **busy reader act fast**. Its job is not to show your work — it is to deliver the answer and just enough support that the reader can trust it and move. Optimize for the reader's time, not for completeness.

## 1. Lead with the bottom line (BLUF)

The **first sentence answers the question.** State the conclusion or recommendation outright, before any background. Everything after it is support. Never open with setup, history, or "first, some context" — a reader who stops after one line should still have the answer.

- Good: *"Ship on SQLite now and plan a Postgres migration later."*
- Bad: *"There are several factors to consider when choosing a database…"*

If there's a single recommended action, say it and say it plainly. If the honest answer is "it depends," lead with the pivot: *"Use X if A, Y if B"* — that is still a bottom line.

## 2. Then support it, point-first

After the bottom line, give the evidence in **short sections or bullets, each led by its point, then the detail.** The reader should be able to skim the lead of each block and get the argument; the detail is there for when they want to go deeper on one point.

- One idea per block. Bold or lead with the takeaway, then explain.
- Order by what matters most to the decision, not by the order you discovered things.

## 3. Attribute the load-bearing claims

Any claim the reader's decision rests on gets **attributed to its source inline**, and that source's URL goes into `citations`. Decorative or common-knowledge statements don't each need a footnote; the load-bearing ones do. This is what lets the reader trust the brief without re-doing the research.

## 4. Separate fact from your read

When you draw a conclusion the inputs imply but don't state outright, frame it as your synthesis ("this suggests…", "taken together…"), not as a sourced fact. The reader needs to know which parts are established and which are your judgment.

## 5. Flag uncertainty plainly

Don't overstate. Where evidence is thin, mixed, or dated, say so in plain words — *"evidence is mixed"*, *"as of <date>"*, *"only one source covers this, treat as preliminary"* — and make sure your `confidence` matches those caveats. A reader trusts a brief that admits its limits more than one that sounds artificially certain.

## 6. Cut hard

Tightness is the whole point. **Cut anything that doesn't change the reader's understanding** or the decision. No padding, no hedging filler, no restating the question, no "in conclusion." If a sentence doesn't move the reader toward acting, delete it. A brief is short by definition; length is a failure mode, not thoroughness.

## 7. Format for the eye

Light markdown that aids skimming: a bolded bottom line, short paragraphs or bullets with bolded leads, and tables **only** for genuinely tabular comparisons. Don't decorate; structure so the argument is visible at a glance. Write the piece itself — never a meta-description of it ("In this brief I will…").

## Shape at a glance

1. **Bottom line** (1–2 sentences) — the answer/recommendation.
2. **Support** — point-first sections/bullets, load-bearing claims attributed, fact vs. inference kept distinct.
3. **Caveats** — uncertainty flagged where real, reflected in confidence.
4. Everything that doesn't serve 1–3 is cut.
