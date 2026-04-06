# Research: How Linear MCP Affects Token Consumption

**Date:** 2026-04-06  
**Status:** Research plan

---

## Research Question

How does Linear MCP affect token consumption in this repository?

The goal is to determine whether enabling Linear MCP materially changes the
average token cost of work in `codex-metrics`, and whether that effect is large
enough to influence the keep/disable decision.

## Working Hypothesis

Linear MCP may increase token consumption by adding extra context, tool calls,
or workspace-search steps to a session. It may also reduce wasted work by
improving task selection and issue clarity.

Because of that tradeoff, the answer should not rely on intuition alone.
We should compare observed token usage before and after the enable point.

## Step 1: When Linear MCP Was Enabled

Best verified enable timestamp:

- `2026-04-02T19:46:21+03:00`

Source used:

- filesystem mtime of `/Users/viktor/.codex/skills/linear/SKILL.md`

Why this is the current best date:

- the repository itself does not contain an earlier explicit `Linear MCP`
  enablement note
- the local Linear skill file is the first durable instruction source I could
  verify on disk that explicitly contains the MCP setup flow

Confidence:

- `medium`

Important caveat:

- this is a best-available instruction timestamp, not a commit-backed repo
  change
- if we later find a more exact config/history event for MCP activation, this
  date should be replaced

## Step 2: Equal 4-Day Windows

To reduce the effect of older history and other token-savings work, compare the
4-day window before the enable point with the 4-day window after it.

Window boundaries:

- Before window: `2026-03-29T19:46:21+03:00` through
  `2026-04-02T19:46:21+03:00`
- After window: `2026-04-02T19:46:21+03:00` through
  `2026-04-06T19:46:21+03:00`

### All Threads With Token Data

- Before: `12` threads, average `15,425,231.25` total tokens, median
  `9,790,008.50`
- After: `11` threads, average `11,382,816.09` total tokens, median
  `2,974,859.00`

### `gpt-5.4-mini` Only

- Before: `10` threads, average `12,962,370.00` total tokens, median
  `9,790,008.50`
- After: `11` threads, average `11,382,816.09` total tokens, median
  `2,974,859.00`

### Preliminary Read

- The equal-window view is cleaner than the full-history view.
- On the repo-wide 4-day window, average token usage is down by about `26%`
  after the cutoff, and the median drops by about `70%`.
- On the `gpt-5.4-mini` slice, average token usage is down by about `12%`
  after the cutoff, and the median still drops sharply.
- This is still not causal proof that Linear MCP itself reduced tokens; it is
  only a directional signal that the post-MCP period looks cheaper on the
  observed repo-local sample.

## Step 3: Compare Similar Task Classes

The closest comparable class I can isolate from thread titles is the
`research_metrics` group:

- product / hypothesis work
- metrics / token / model analysis
- documentation and telemetry research

This class is a better apples-to-apples proxy than the full window because it
excludes unrelated general work and focuses on the same kind of investigation
threads that dominate both periods.

### `research_metrics` Class, `gpt-5.4-mini` Only

- Before: `7` threads, average `9,494,126.29` total tokens, median
  `9,816,847.00`
- After: `6` threads, average `13,745,529.33` total tokens, median
  `9,930,681.50`

### Read on the Comparable Class

- The median is basically flat, which suggests the “typical” research/metrics
  session did not materially get more expensive after the cutoff.
- The average increases after the cutoff because the after window includes a few
  very large research/system sessions.
- That means the comparable-class data does **not** show a clean token-cost win
  from Linear MCP, but it also does not show a clear typical-session penalty.
- The most defensible interim read is: Linear MCP is not obviously driving up
  the typical research-session token cost, yet the average cost impact is
  noisy enough that we should avoid a hard keep/disable decision from this
  sample alone.

## Planned Method

1. Find the exact date when Linear MCP was enabled in repository instructions or
   other local documentation.
2. Measure average token consumption before that date.
3. Measure average token consumption after that date.
4. Compare the two periods and decide whether Linear MCP should stay enabled,
   be adjusted, or be disabled.

## Measurement Rules

- Use local metrics and history as the source of truth.
- Prefer explicit dates over approximate periods.
- Prefer averages over raw totals when comparing before/after behavior.
- Keep the comparison scoped to the same repository so the result is not mixed
  with unrelated projects.
- Record uncertainty if the enable date cannot be established precisely.

## Suggested Metrics

Primary:

- average tokens per closed goal
- average tokens per attempt
- average tokens per successful goal

Secondary:

- attempts per closed goal
- review coverage
- exact-fit / partial-fit mix
- model mix during the comparison window

## Important Caveats

- A simple before/after comparison can be confounded by changes in task mix.
- Model changes, policy changes, and history coverage changes may all affect
  token usage independently of Linear MCP.
- A stronger conclusion would compare the same task classes on both sides of the
  enable date, not just the repository-wide average.

## Expected Output

The research result should answer:

- when Linear MCP was enabled
- whether average token usage increased, decreased, or stayed roughly flat
- whether any observed change is likely to be caused by Linear MCP itself or by
  another overlapping workflow change
- whether the evidence supports keeping Linear MCP enabled

## Interim Result

Current read:

- **keep Linear MCP enabled for now**

Reasoning:

- the equal-window comparison does not show a stable typical-session token
  increase
- the closest comparable `research_metrics` class has a nearly flat median
- the observed average differences are noisy and appear to be driven by a few
  large sessions rather than a consistent broad penalty
- there is not enough evidence here to justify disabling Linear MCP purely on
  token cost

Confidence:

- `low-medium`

What would change this recommendation:

- a longer post-cutoff sample that shows a persistent median increase
- a controlled comparison inside the same task class with more matched samples
- evidence that Linear MCP causes repeated waste, retries, or worse outcome fit

## Notes

- This is a research plan, not a conclusion.
- If the enable date cannot be verified, the analysis should explicitly say so
  before making any recommendation.
