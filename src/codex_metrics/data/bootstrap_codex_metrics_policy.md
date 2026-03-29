# Codex Metrics Policy

This policy defines the minimum workflow for tracking Codex-assisted engineering work in a repository.

The local `AGENTS.md` should point agents to this file.
Put the operational rules for codex-metrics here, not in duplicated AGENTS prose.

## What This Is

`codex-metrics` is the repository-local system for tracking:

- requested outcomes as goals
- implementation passes and retries as attempts
- final success or failure state
- optional token and USD cost signals

Use it to make Codex-assisted work auditable instead of leaving the history only in chat transcripts.

## When It Applies

Follow this policy for meaningful Codex-assisted engineering work in this repository.

That normally includes:

- product or engineering delivery
- bug fixes
- refactors
- tooling changes
- retrospective writeups

Do not treat it as optional bookkeeping after the fact. Goal tracking is part of the task workflow itself.

## Purpose

Use this policy to answer four practical questions:

1. Are requested outcomes being completed successfully?
2. How much retry pressure was required?
3. What failure modes keep repeating?
4. What known token or USD cost was spent?

## Core Rules

- Metrics bookkeeping is mandatory.
- Metrics bookkeeping is mandatory for Codex-assisted engineering work.
- Track one requested outcome as one goal.
- Track retries and implementation passes as attempt history, not as separate unrelated goals.
- Do not manually edit generated metrics files when the CLI can regenerate them.
- Summary values must be derived from stored records, not hand-written.

## Source Of Truth

- Structured metrics: `metrics/codex_metrics.json`
- Generated report: `docs/codex-metrics.md`

If they disagree, the structured metrics file wins.

## Key Terms

- `goal`: one requested outcome or task
- `attempt`: one implementation pass, retry, or meaningful follow-up on that goal
- `goal_type`: whether the work is `product`, `retro`, or `meta`
- `failure_reason`: the main reason a failed attempt or failed goal did not succeed

## Required Goal Workflow

### First Task Checklist

When you start working in a bootstrapped repository:

1. Confirm how to invoke the CLI in this repository.
2. Read this policy before changing code.
3. Start or continue the correct goal before doing substantial implementation work.
4. Update the same goal as you continue, instead of creating unrelated duplicate goals for retries.

### At Goal Start

1. Create or continue the correct goal.
2. Set `goal_type` explicitly for new goals.
3. Set status to `in_progress`.
4. Start attempts at `0`.

### On Each Attempt

1. Increment attempts.
2. Record notes when useful.
3. Record cost or tokens when known.
4. Record one dominant failure reason when the attempt failed.

### On Goal Completion

1. Set final status to `success` or `fail`.
2. Set `finished_at`.
3. Recompute summary values.
4. Regenerate the report.

## Allowed Goal Types

- `product`
- `retro`
- `meta`

Use:

- `product` for delivery work
- `retro` for retrospective analysis and writeups
- `meta` for bookkeeping, policy, audits, and tooling governance

## Validation Rules

- `success` must not have `failure_reason`
- `fail` must have `failure_reason`
- closed goals must have at least one attempt
- `finished_at` must be empty for `in_progress`
- `finished_at` must not be earlier than `started_at`

## Standard Commands

Use `codex-metrics ...` if the CLI is installed on `PATH`.
If you are using a standalone self-host binary that is not on `PATH`, invoke it by filesystem path instead, for example `./codex-metrics ...` or `/path/to/codex-metrics ...`.
On macOS/Linux, prefer one shared entrypoint at `~/bin/codex-metrics`.
If you have a standalone binary, run `/path/to/codex-metrics install-self` to create it instead of copying the binary into each repository.

Initialize the scaffold:

```bash
codex-metrics bootstrap
```

Create or continue a goal:

```bash
codex-metrics update --title "Add CSV import" --task-type product --attempts-delta 1
```

Record a retry or another implementation pass on the same goal:

```bash
codex-metrics update --task-id <goal-id> --attempts-delta 1 --notes "Retry"
```

Close a goal:

```bash
codex-metrics update --task-id <goal-id> --status success --notes "Validated"
```

Review the current summary:

```bash
codex-metrics show
```
