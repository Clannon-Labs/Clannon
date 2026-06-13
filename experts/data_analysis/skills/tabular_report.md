---
description: How to present a data analysis as a clear, table-led report a reader can act on. Load when writing up findings into full_content.
---

# Skill: reporting a data analysis

The reader wants the answer and the numbers behind it, fast. Lead with the finding,
support it with tables, and be honest about the limits.

- **Headline first.** Open with the bottom-line finding in one or two sentences — the
  answer to the question, with the single most important number. Not "here is some
  analysis"; the actual conclusion.
- **Tables for numbers.** Put figures in markdown tables, not buried in prose: summary
  statistics, period-over-period breakdowns, top/bottom-N, outlier rows. One table per
  idea; label units and periods.
- **Call out what matters.** Name the trend, the outlier, the surprising value — and
  quantify it ("March is 3.2× the median month"). Don't make the reader find it.
- **Separate fact from inference.** The computed numbers are fact; "this suggests
  demand is seasonal" is your inference — frame it as such, not as data.
- **State the caveats.** Sample size, missing data, outliers skewing an average, a
  short time window, a correlation that isn't causation. A trustworthy analysis names
  its own limits, and they should be reflected in `confidence`.
- **Tie it back to the question.** End on what the analysis means for what was asked —
  the actionable takeaway, grounded in the numbers above.
