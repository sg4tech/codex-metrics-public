# Codex Metrics Policy

This document defines the mandatory minimum policy for tracking Codex-assisted engineering work.

Use it as the operating contract for repositories that adopt `codex-metrics`.

## Purpose

Use this policy to answer four practical questions:

1. Are requested outcomes being completed successfully?
2. How much retry pressure was required?
3. What failure modes keep repeating?
4. What known cost was spent?

Metrics bookkeeping is mandatory.

## Scope

Apply this policy when Codex materially contributes to an engineering outcome, including:

- code changes
- configuration changes
- test changes
- script changes
- bug fixes
- retrospective writeups
- tooling or process work

## Core Model

- A `goal` is one requested outcome.
- An `attempt` is one implementation pass, retry, or inferred history record for the same goal.
- Goals represent requested outcomes.
- Attempts preserve retry history and failure visibility.
- Summary reporting must be derived from stored records, not edited manually.

## Allowed Goal Types

- `product` for delivery work
- `retro` for retrospective analysis and writeups
- `meta` for bookkeeping, policy, audits, tooling governance, and support work

Always set `goal_type` explicitly for new goals.

If a new goal intentionally continues or supersedes a prior closed goal, record that link explicitly.

Do not change `goal_type` in place after attempt history already exists. Start a new linked goal instead.

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

The structured metrics file is the source of truth.

For this repository:

- source of truth: `metrics/codex_metrics.json`
- generated report: `docs/codex-metrics.md`

If they disagree, the structured metrics file wins.

Do not edit generated metrics files manually when the CLI can regenerate them.

## Required Workflow

### At Goal Start

1. Detect whether the work belongs to an existing goal or a new goal.
2. Create a new goal if needed.
3. Set status to `in_progress`.
4. Initialize attempts to `0`.

### On Each Attempt

1. Increment `attempts`.
2. Update notes when useful.
3. Update cost or token data when available.
4. Record the dominant failure reason if the attempt did not succeed.

### On Goal Completion

1. Set final status to `success` or `fail`.
2. Set `finished_at`.
3. Ensure cost and token totals are updated when available.
4. Regenerate the human-readable report.

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

## Reporting Rules

- Goal-level success must not hide retry pressure.
- Product, retro, and meta work must remain distinguishable.
- Inferred failed attempts may preserve history shape, but they must not pollute diagnostic failure-reason reporting.

## Anti-Gaming Rules

- Do not split one coherent goal into many tiny goals to inflate success rate.
- Do not classify bookkeeping or retrospective work as product delivery.
- Do not keep failed work as `in_progress` forever to hide failure.
- Do not mark a goal as success before validation is complete.
