# 2026-03-29 Cost Coverage Audit Retro

## Situation

We already had cost reporting, known-vs-complete coverage, and operator review messaging.

But the product question was still unresolved:

- why is cost coverage still low on product goals
- is the bottleneck in reporting, sync logic, or operator workflow

We needed a diagnostic layer that could explain missing coverage instead of only reporting that coverage was low.

## What Happened

We added a new read-only `audit-cost-coverage` command and a dedicated `cost_audit` module.

The command classifies closed product goals into actionable buckets such as:

- `sync_gap`
- `partial_stored_coverage`
- `thread_unresolved`
- `no_usage_data_found`
- `telemetry_unavailable`
- `incomplete_goal_window`

After running it on the real history, the output showed that the dominant failure mode was not reporting or summary math.

The dominant pattern was:

- `no_usage_data_found`

That means current cost weakness is mostly a capture/recovery problem, not a presentation problem.

## Root Cause

The earlier cost layer was strong enough to say:

- coverage is partial

But not strong enough to say:

- why coverage is partial

So we had observability at the KPI layer, but not at the constraint-diagnosis layer.

## 5 Whys

1. Why was `cost coverage` still weak?
   Because most product goals still had no stored cost or token totals.

2. Why did we not know what to fix next?
   Because the system reported low coverage, but did not classify missing-coverage causes.

3. Why was that a product problem?
   Because PM decisions need bottleneck diagnosis, not just summary numbers.

4. Why did we not already have that diagnosis?
   Because earlier work focused on honest reporting semantics first: known vs complete coverage, covered-subset averages, and operator review.

5. Why was the next step then different?
   Because once reporting became honest enough, the real constraint moved from presentation to capture/recovery.

## Theory Of Constraints

The previous constraint was:

- misleading or brittle cost reporting

The new constraint, revealed by the audit, is:

- missing recoverable usage data for product goals under current workflow and matching rules

So optimizing reporting further would now be non-bottleneck work.

The next leverage point is:

- cost capture and recovery workflow

## Retrospective

This was a good example of not over-solving the wrong layer.

We did not jump straight into new cost metrics or more summary variants.
We added a read-only diagnostic layer first.

That turned a vague concern:

- "cost is still incomplete"

into a concrete operational insight:

- "the dominant cost problem is `no_usage_data_found`"

That is a much better product and engineering handoff.

## Conclusions

- cost reporting semantics were not the main remaining problem
- a separate diagnostic audit layer was the right next step
- the current bottleneck is cost capture/recovery, not summary presentation
- future cost work should focus on workflow, matching rules, and recoverability before adding more KPI polish

## Permanent Changes

- keep `audit-cost-coverage` as a first-class diagnostic command
- treat cost coverage diagnosis as a separate concern from summary reporting
- when coverage is low, first determine the dominant reason bucket before changing metrics semantics
- prefer bottleneck-revealing audits over more top-line KPI polish when the next fix is unclear
