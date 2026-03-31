# Retrospective: Product-First Summary Redesign

## Situation

`codex-metrics` already had strong internal tracking, but its most visible surfaces still led with an overly flattering operational picture:

- `Success Rate`
- aggregate cost
- overall closure counts

That made the product less useful than it could be for the real decision:

- are we getting the requested outcome more reliably?

## What Happened

The summary surfaces were redesigned so that both:

- CLI `show`
- generated `docs/codex-metrics.md`

now start with a `Product quality` section instead of a global closure summary.

The new section surfaces:

- reviewed `result_fit` coverage
- `exact_fit / partial_fit / miss / unreviewed`
- product-only retry pressure
- product-only cost context

The older global closure and cost metrics were preserved, but moved into a secondary `Operational summary` section.

## QA

QA checks performed:

- `make verify` passed with `152` tests
- live CLI smoke via `./tools/codex-metrics show`
- markdown output inspection in `docs/codex-metrics.md`
- regression checks for:
  - empty show output
  - reviewed product quality output
  - report section order
  - product cost-per-success semantics

QA result:

- the redesign is working as implemented
- CLI and markdown report are aligned
- the new reporting test is included in canonical `make verify`

## Product Demo

Before:

- the first visible message was effectively “everything is 100% successful”
- quality truth lived lower in the stack or only in audits/history

After:

- the first visible block now answers:
  - how many product goals are reviewed
  - how many were `exact_fit`
  - how many were `partial_fit`
  - how much is still unreviewed
  - how much retry pressure exists on product work

This is meaningfully closer to the operator's real question than the previous first screen.

## Root Cause

The previous product weakness was not a data-collection failure.

The data already existed:

- `result_fit`
- product/meta/retro split
- retry history
- product-only cost slices

The real issue was presentation priority:

- the product led with closure metrics
- the more decision-useful quality truth was secondary or implicit

## 5 Whys

1. Why did the summary feel too optimistic?
   - Because it led with global success and closure numbers.
2. Why was that misleading?
   - Because those numbers reflect operational closure more than outcome fit.
3. Why did product truth stay secondary?
   - Because the reporting surface had not been redesigned after adding `result_fit`.
4. Why had that redesign not happened yet?
   - Because earlier work focused on data correctness, coverage, and audits first.
5. Why was the redesign needed now?
   - Because once the data was trustworthy enough, the bottleneck moved to what the product emphasized first.

## Theory of Constraints

The constraint was no longer metrics correctness.

The constraint had moved to product presentation:

- the most visible screen still optimized for bookkeeping-style interpretation
- the most useful product truth was not the first thing a user saw

So adding more collection logic or more audits would have optimized a non-constraint.

## Product Evaluation

Did we get what was needed?

Mostly yes.

What clearly improved:

- the product now foregrounds quality truth instead of raw closure
- quality review coverage is explicit
- product-only retry pressure is visible
- product-only cost context is visible without pretending cost is the north star

What is still incomplete:

- the operator review block still leans more operational than product-quality-first
- `result_fit` coverage is still partial in live data, so the new section is honest but not yet complete
- there is still no dedicated compare view for multiple projects

So the outcome is good and valuable, but it is not the final product presentation endpoint.

## Conclusions

- The redesign solved the right problem at the right layer.
- Product-first reporting is a meaningful improvement over closure-first reporting.
- The best next product step is not more summary churn, but using this new surface to observe whether it changes decisions.

## Permanent Changes

- `show` now leads with `Product quality`.
- `docs/codex-metrics.md` now leads with `Product quality`.
- Product cost-per-success in the new quality section excludes failed-goal cost.
- `tests/test_reporting.py` is now part of canonical verification.
