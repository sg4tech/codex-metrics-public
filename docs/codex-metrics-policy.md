# Codex Metrics Policy

This document defines the mandatory minimum policy for tracking AI-agent-assisted engineering work.

Use it as the operating contract for repositories that adopt `codex-metrics`.

## Purpose

Use this policy to answer four practical questions:

1. Are requested outcomes being completed successfully?
2. How much retry pressure was required?
3. What failure modes keep repeating?
4. What known cost was spent?

Metrics bookkeeping is mandatory.

## Scope

Apply this policy when an AI agent materially contributes to an engineering outcome, including:

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
- optional export: `docs/codex-metrics.md`

If they disagree, the structured metrics file wins.

Do not edit generated metrics files manually when the CLI can regenerate them.

## Required Workflow

### Linear-First Intake

Before any substantial implementation or documentation work begins, create or update the corresponding Linear issue and record the requirements there.

The issue should contain, at minimum:

1. the requested outcome
2. the acceptance criteria
3. any relevant links, files, or follow-up questions

Do not start coding until the work is represented in Linear. If the scope changes mid-stream, update the issue first and continue through that issue rather than drifting into undocumented work.

### Commit Subject Rules

Use a Linear-linked commit subject for engineering work:

- `CODEX-123: summary`

If a change is intentionally not tied to a Linear issue, use the explicit no-task prefix instead:

- `NO-TASK: summary`

Do not use an unmarked free-form commit subject for engineering work. The validator should reject subjects that omit both prefixes.

### At Goal Start

1. Detect whether the work belongs to an existing goal or a new goal.
2. Create a new goal if needed.
3. Set status to `in_progress`.
4. Initialize attempts to `0`.
5. Do this before substantial implementation, documentation, or validation work begins. Do not postpone task start bookkeeping until after meaningful progress already exists.

### On Each Attempt

1. Increment `attempts`.
2. Update notes when useful.
3. Update cost or token data when available.
4. Record the dominant failure reason if the attempt did not succeed.

### On Goal Completion

1. Set final status to `success` or `fail`.
2. Set `finished_at`.
3. Ensure cost and token totals are updated when available.
4. Regenerate the optional markdown report only when that export is actually needed.

## Recommended Commands

Prefer the high-level task workflow commands:

```bash
codex-metrics start-task --title "Add CSV import" --task-type product
codex-metrics continue-task --task-id <goal-id> --notes "Retry after review"
codex-metrics finish-task --task-id <goal-id> --status success --notes "Validated"
codex-metrics ensure-active-task
codex-metrics show
codex-metrics render-report
codex-metrics sync-usage
codex-metrics ingest-codex-history --help
codex-metrics normalize-codex-history --help
codex-metrics derive-codex-history --help
codex-metrics compare-metrics-history
```

The public workflow contract should stay agent-agnostic. Provider-specific detection and telemetry support belong behind internal adapters, not in required public CLI flags.

Automatic local usage sync is currently implemented for Codex telemetry. Other agents are still in scope for the product, but their support should land through the same universal command surface.

When repository work has already started but no active task exists yet, prefer `codex-metrics ensure-active-task` before continuing with active-work commands.
Closed-goal repair via `finish-task` or a status-closing `update` remains available for history correction, but it should stay narrow and explicit.

If `codex-metrics` is expected but unavailable, treat that as an `environment_issue` or installation mismatch and report it clearly.

Do not invent a manual fallback workflow and do not edit generated metrics artifacts directly just to keep moving.

Use raw `update` only when you need a lower-level or less common mutation path.

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
