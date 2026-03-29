# Codex Metrics Policy

This document defines the mandatory policy for measuring Codex-driven engineering work.

It is written to be reusable across projects. Repository-specific defaults for this repo are included only where needed.

## Purpose

The policy exists to answer four questions reliably:

1. Are requested outcomes being completed successfully?
2. How much retry pressure is required to get there?
3. What are the dominant failure modes?
4. What known cost was spent to achieve the result?

The policy optimizes for:

- trustworthy delivery reporting
- low retry count
- visible failure modes
- practical cost visibility

## Scope

Apply this policy to engineering work where Codex materially contributes to a user-visible or developer-visible outcome, including:

- code changes
- configuration changes
- test changes
- script changes
- bug fixing
- implementation work

## Core Principles

- Metrics bookkeeping is mandatory.
- Metrics are tracked per goal, not per message.
- Summary values must always be derived from stored records, not edited manually.
- A goal is not done until metrics and reporting are updated.
- Honest partial visibility is better than brittle all-or-nothing reporting.
- Goal-level success must not hide retry pressure from the underlying attempt history.
- Product, retrospective, and meta work should remain distinguishable in stored records and reporting.

## Core Model

### Goal

One requested outcome.

A goal may require multiple attempts or linked follow-up goals.

### Attempt Entry

One execution pass or inferred history record for the same goal.

Entries exist to preserve attempt history and failure visibility. They are not a mirrored copy of final goal state.

Use goals and entries together as the source model:

- goals represent requested outcomes
- entries represent attempt history
- summary reporting should be derived from effective goal chains, not raw duplicated records

### Success

A goal is `success` when:

- the intended outcome is implemented
- required validation is complete
- the result is accepted

### Fail

A goal is `fail` when:

- the goal is abandoned
- the result is unusable
- the goal cannot be completed in the current session
- the work must restart as a new goal instead of continuing

### Cost

Cost is total resource usage across the goal chain.

Preferred order:

1. USD cost
2. token count
3. null if neither is available

## Required Goal Fields

Each goal record must contain:

- `goal_id`
- `title`
- `goal_type`
- `supersedes_goal_id`
- `status`
- `attempts`
- `started_at`
- `finished_at`
- `cost_usd`
- `tokens_total`
- `failure_reason`
- `notes`

Optional goal-review field:

- `result_fit` for closed `product` goals when the operator wants to record whether the delivered result was an exact fit, a partial fit, or a miss

## Required Entry Fields

Each entry record must contain:

- `entry_id`
- `goal_id`
- `entry_type`
- `status`
- `started_at`
- `finished_at`
- `cost_usd`
- `tokens_total`
- `failure_reason`
- `notes`

Optional inferred history is allowed, but inferred failed entries must not pollute diagnostic failure-reason reporting.

## Allowed Goal Types

- `product`
- `retro`
- `meta`

Use:

- `product` for delivery work
- `retro` for retrospective analysis and writeups
- `meta` for bookkeeping, policy, audits, tooling governance, and support work

Rules:

- always set `goal_type` explicitly for new goals
- for new goals, prefer generated goal ids; reserve explicit ids for updating existing goals, imports, or historical backfill
- if a new goal intentionally continues or supersedes a prior closed goal, record the link explicitly
- once attempt history exists, do not change `goal_type` in place; start a new linked goal instead

## Allowed Status Values

- `in_progress`
- `success`
- `fail`

## Allowed Failure Reasons

- `unclear_task`
- `missing_context`
- `validation_failed`
- `environment_issue`
- `model_mistake`
- `scope_too_large`
- `tooling_issue`
- `other`

Use one primary reason for a failed goal or failed attempt.

## Source Of Truth

The source of truth is the structured metrics file.

For this repository:

- source of truth: `metrics/codex_metrics.json`
- generated human-readable report: `docs/codex-metrics.md`

If there is a mismatch, the structured metrics file wins.

## Required Workflow

### At Goal Start

1. Detect whether the work belongs to an existing goal or a new goal.
2. Create a new goal if needed.
3. If the new goal intentionally replaces or continues a prior closed goal, record that link explicitly.
4. Set status to `in_progress`.
5. Initialize attempts to `0`.

### On Each Attempt

1. Increment `attempts`.
2. Update notes if useful.
3. Update partial cost if available.
4. Record the dominant failure reason if the attempt did not succeed.
5. Append or update attempt-history entries so retry pressure stays visible.

### On Goal Completion

1. Set final status to `success` or `fail`.
2. Set `finished_at`.
3. Ensure cost and token totals are updated if available.
4. Recompute summary metrics.
5. Regenerate the human-readable report.

For `product` goals, record timestamps close to the real work window when practical.
Avoid post-hoc zero-duration closeouts that make later cost recovery less reliable.

## Validation Rules

Use strict validation. Invalid state must fail loudly.

At minimum:

- `success` must not have `failure_reason`
- `fail` must have `failure_reason`
- closed goals must have at least one attempt
- `finished_at` must be empty for `in_progress`
- `finished_at` must not be earlier than `started_at`
- linked supersession references must resolve
- supersession graphs must remain acyclic

Apply the same business honesty to entry records where relevant.

## Testing Standard

For mutating commands such as update, merge, and sync flows, cover three test buckets when practical:

1. happy path
2. invalid-state rejection
3. summary and report consistency after mutation

When the repository provides a canonical local verify entrypoint, prefer it.

For this repository, the standard command is:

```bash
make verify
```

Dependent updater commands must be validated sequentially, not in parallel.

## Summary Metrics

Recalculate summary metrics after every closed effective goal.

They must be available:

- overall
- per `goal_type`

Reports must surface both:

- effective goal outcomes
- raw entry-level retry pressure

### Success Rate

`success_rate = successes / closed_goals`

Where:

- `successes` = effective goals with status `success`
- `closed_goals` = effective goals with status `success` or `fail`

If `closed_goals = 0`, set to `null`.

### Attempts Per Closed Goal

`attempts_per_closed_goal = total_attempts / closed_goals`

If `closed_goals = 0`, set to `null`.

### Failure Reasons

Count failure reasons from diagnostic failed entries only.

Inferred attempt-history entries may preserve history shape, but they must not pollute diagnostic failure-reason reporting.

## Product Quality Review

For `product` goals, an optional operator-reviewed `result_fit` field may be used to distinguish:

- `exact_fit`
- `partial_fit`
- `miss`

This field is meant to complement, not replace, operational `success` and `fail` status.

Use it when the operator needs to distinguish:

- goals that closed successfully but still required corrective work
- explicit misses
- exact outcome matches

Do not count synthetic inferred failures created only to preserve attempt history shape.

### Known Cost Coverage

Track how many successful effective goals have any known cost.

Required fields:

- `known_cost_successes`
- `known_token_successes`

### Known Cost Per Success

Average cost across successful effective goals with any known cost.

Required fields:

- `known_cost_per_success_usd`
- `known_cost_per_success_tokens`

### Complete Cost Coverage

Track how many successful effective goals have full chain-complete cost coverage.

Required fields:

- `complete_cost_successes`
- `complete_token_successes`

### Complete Cost Per Covered Success

Average cost across the successful effective goals whose chains are fully covered.

Required fields:

- `complete_cost_per_covered_success_usd`
- `complete_cost_per_covered_success_tokens`

This is a strict subset metric. It should not require complete coverage across all repository history.

## Reporting Standard

At task completion, the final response should report at least:

- goal status
- goal type
- attempts
- current success rate
- current attempts per closed goal
- current cost metrics when available

Human-readable reporting should make the following visible:

- goal-level outcome summary
- entry-level summary
- failure reasons
- cost coverage semantics when data is partial

## Anti-Gaming Rules

- Do not split one coherent goal into many tiny goals to inflate success rate.
- Do not classify retrospective or bookkeeping work as product delivery.
- Do not keep failed work as `in_progress` forever to hide failure.
- Do not mark a goal as success before validation is complete.
- Do not edit summary fields directly without updating the underlying records.
- Do not let a pretty goal summary hide failed attempts underneath.

## Repository Defaults For This Repo

This repository currently uses:

- `AGENTS.md` for local operating rules
- `docs/codex-metrics-policy.md` for this policy
- `metrics/codex_metrics.json` as source of truth
- `docs/codex-metrics.md` as generated report

Generated metrics files should be treated as production-like artifacts. Prefer temporary paths for destructive smoke checks unless the task explicitly requires regenerating tracked files.
