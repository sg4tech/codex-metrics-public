# Codex Metrics Policy

This file defines the mandatory metrics policy for AI-driven development tasks.
Its rules are part of the project operating instructions and must be followed on every task.

## Purpose

The goal of this policy is to measure how effectively tasks are completed through Codex without manual code editing.

This policy optimizes for:
- reliable task completion
- low retry count
- reasonable cost per completed task
- visibility into the main failure modes

## Scope

This policy applies to every engineering task performed through Codex.

A task is considered in scope if Codex:
- changes code
- changes configuration
- changes tests
- changes scripts
- performs implementation or bug fixing work intended to produce a user-visible or developer-visible result

## Core principles

- Metrics bookkeeping is mandatory.
- Metrics are tracked per task, not per message.
- Manual code editing by the user is assumed to be zero.
- A task is not done until its metrics are updated.
- Summary metrics must always be derived from task records, not edited manually.

## Definitions

### Goal
One user-visible or developer-visible requested outcome.

Examples:
- add CSV import for portfolio data
- fix login redirect bug
- add test coverage for billing service

A goal may require multiple attempts or linked follow-up records.

### Attempt
One independent Codex execution cycle for the same goal.

A new attempt starts when Codex takes a new implementation pass after failure, clarification, rollback, or a significant re-plan.

### Success
A goal is marked as `success` when:
- the intended outcome is implemented
- required validation has been completed
- the result is accepted
- no manual code edits were required from the user

### Fail
A goal is marked as `fail` when:
- the goal is abandoned
- the goal is reverted
- the goal cannot be completed in the current session
- the result is unusable after attempts
- the goal must be restarted as a new goal instead of continued

### Cost
Cost is the total resource usage across all attempts for the goal.

Preferred order:
1. USD cost
2. token count
3. if neither is available, keep cost as null

## Required goal fields

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

## Required entry fields

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

Entries are attempt-history records.
They must not be treated as a mirrored copy of final goal state when the goal has multiple attempts.

## Allowed goal types

- `product`
- `retro`
- `meta`

Use:
- `product` for product or engineering delivery
- `retro` for retrospectives and retrospective writeups
- `meta` for bookkeeping, audits, policy/tooling governance, and other support work that should not be mixed with product delivery metrics

For new goal records, `goal_type` must always be set explicitly.
If a new goal intentionally continues or supersedes a prior closed goal instead of remaining one goal with more attempts, that relationship must be recorded explicitly.

## Allowed status values

- `in_progress`
- `success`
- `fail`

## Allowed failure reasons

Use one primary reason when a task fails, or when an extra attempt was needed.

- `unclear_task`
- `missing_context`
- `validation_failed`
- `environment_issue`
- `model_mistake`
- `scope_too_large`
- `tooling_issue`
- `other`

## Source of truth

The source of truth for metrics is:

`metrics/codex_metrics.json`

Human-readable summaries may also be written to:

`docs/codex-metrics.md`

If there is any mismatch, `metrics/codex_metrics.json` is the source of truth.

Generated metrics files are production-like artifacts for this repository.
During validation, destructive smoke checks such as `init` should prefer temporary metrics/report paths unless the task explicitly requires regenerating the tracked repository files.

## Required per-goal workflow

### At goal start
Codex must:
1. detect whether the work belongs to an existing open goal or a new goal
2. create a new goal record if needed
3. if a new goal intentionally replaces or continues a prior closed goal, record that link explicitly
4. set status to `in_progress`
5. initialize attempts to `0`

### On each attempt
Codex must:
1. increment `attempts`
2. update notes if useful
3. update partial cost if available
4. record the dominant failure reason if the attempt did not succeed
5. append or update attempt-history entry data so entry-level reporting remains diagnostic

### On goal completion
Codex must:
1. set final status to `success` or `fail`
2. set `finished_at`
3. ensure total cost fields are updated if available
4. recompute summary metrics
5. update the human-readable report

## Summary metrics

The following summary metrics must be recalculated after every closed effective goal.

They must be available both:
- overall
- per `goal_type`

Reports must not present effective goal-level success alone when the raw entry history still contains failed attempts.
Entry-level summary and failure reasons should remain visible alongside goal-level summary so retry pressure is not hidden by supersession or successful later replacements.

### Success Rate
Formula:

`success_rate = successes / closed_goals`

Where:
- `successes` = number of effective goals with status `success`
- `closed_goals` = number of effective goals with status `success` or `fail`

If `closed_goals = 0`, set `success_rate = null`.

### Attempts per Closed Goal
Formula:

`attempts_per_closed_task = total_attempts / closed_goals`

Where:
- `total_attempts` = sum of attempts across closed effective goals
- `closed_goals` = number of effective goals with status `success` or `fail`

If `closed_goals = 0`, set `attempts_per_closed_task = null`.

### Cost per Success (USD)
Formula:

`cost_per_success_usd = total_cost_usd / successes`

If `successes = 0` or cost is unavailable, set `cost_per_success_usd = null`.

### Cost per Success (Tokens)
Formula:

`cost_per_success_tokens = total_tokens / successes`

If `successes = 0` or token data is unavailable, set `cost_per_success_tokens = null`.

## Minimum reporting standard

At the end of each completed task, Codex must provide in its final response:

- goal status
- goal type
- attempts for the goal
- current success rate
- current attempts per closed goal
- current cost per success if available

## Definition of done

A task is not done until all of the following are true:
- implementation work is complete
- validation work is complete
- goal and entry records are updated in `metrics/codex_metrics.json`
- summary metrics are recalculated
- readable report is updated in `docs/codex-metrics.md`

## Anti-gaming rules

- Do not split one coherent goal into many tiny goals just to inflate success rate.
- Do not classify retrospective or bookkeeping work as product delivery.
- Do not keep failed work as `in_progress` forever to hide failures.
- Do not edit summary values directly without updating the underlying goal and entry records.
- Do not mark a goal as success if validation has not been completed.
- Do not ignore bookkeeping because implementation “already works”.

## Preferred file structure

- `AGENTS.md`
- `docs/codex-metrics-policy.md`
- `docs/codex-metrics.md`
- `metrics/codex_metrics.json`

## Recommended JSON structure

```json
{
  "summary": {
    "closed_tasks": 0,
    "successes": 0,
    "fails": 0,
    "total_attempts": 0,
    "total_cost_usd": 0,
    "total_tokens": 0,
    "success_rate": null,
    "attempts_per_closed_task": null,
    "cost_per_success_usd": null,
    "cost_per_success_tokens": null,
    "by_task_type": {
      "product": {},
      "retro": {},
      "meta": {}
    }
  },
  "goals": [
    {
      "goal_id": "2026-03-29-g001",
      "title": "Example task",
      "goal_type": "product",
      "supersedes_goal_id": null,
      "status": "success",
      "attempts": 1,
      "started_at": "2026-03-29T09:00:00+00:00",
      "finished_at": "2026-03-29T09:10:00+00:00",
      "cost_usd": null,
      "tokens_total": null,
      "failure_reason": null,
      "notes": "Example task record"
    }
  ],
  "entries": [
    {
      "entry_id": "2026-03-29-e001",
      "goal_id": "2026-03-29-g001",
      "entry_type": "product",
      "status": "success",
      "started_at": "2026-03-29T09:00:00+00:00",
      "finished_at": "2026-03-29T09:10:00+00:00",
      "cost_usd": null,
      "tokens_total": null,
      "failure_reason": null,
      "notes": "Example entry record"
    }
  ]
}
