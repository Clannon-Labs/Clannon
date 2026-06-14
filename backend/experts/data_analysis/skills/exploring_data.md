---
description: How to explore a structured dataset systematically — shape, types, missing data, summary stats, distributions, outliers, trends. Load when you need to understand an unfamiliar dataset before answering.
---

# Skill: exploring a dataset

Work in this order, computing each step with pandas/numpy and printing the result —
never eyeball the raw data and guess.

- **Shape and structure first.** Load it (`pd.read_csv`/`pd.read_json`). Print
  `df.shape`, `df.dtypes`, and `df.head()`. Know how many rows/columns and what each
  column is before analyzing anything.
- **Data quality.** Check missing values (`df.isna().sum()`), duplicates, and obvious
  bad values (negatives where impossible, dates out of range). Decide how to handle
  them and say what you did — never silently drop data.
- **Summary statistics.** `df.describe(include="all")` for the numeric and categorical
  overview. For key columns, print mean/median/std/min/max and the quartiles.
- **Distributions.** For an important numeric column, look at the spread — quartiles,
  skew, whether the mean is pulled by outliers. For categoricals, `value_counts()`.
- **Outliers.** Flag them with a stated rule (e.g. IQR: outside Q1-1.5·IQR..Q3+1.5·IQR,
  or |z| > 3) and report which rows and how much they move the aggregate.
- **Trends and relationships.** For time series, resample/group and compare periods
  (growth rates, moving averages). For relationships, correlations between numeric
  columns — but say "correlation, not causation."
- **Answer the actual question.** The above is groundwork; focus the depth on what the
  task asked. Report the figures that bear on the answer, with the caveats that matter.
