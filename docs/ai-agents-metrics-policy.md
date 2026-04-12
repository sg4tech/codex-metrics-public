# AI Agents Metrics Policy

This document defines the mandatory minimum policy for tracking AI-agent-assisted engineering work.

Use it as the operating contract for repositories that adopt `ai-agents-metrics`.

## Two-Tier Model

`ai-agents-metrics` operates as a two-tier system:

**Tier 1 — History extraction (primary, no setup required)**

Point the tool at your local agent history directory and run `history-update` + `show`. The tool extracts session structure, retry pressure, token cost, and timeline from existing conversation files — no prior instrumentation required. This is the primary product flow and the primary source of value.

**Tier 2 — Manual tracking (opt-in, for explicit judgements)**

For explicit goal boundaries, outcome classification (`result_fit`), and failure reasons that cannot be reliably inferred from history, the manual `start-task` / `finish-task` / `update` workflow is available as an opt-in enhancement on top of the history layer.

The policy below applies to repositories that adopt both tiers. For repositories that use history extraction only, the Required Workflow section applies only to the goal boundaries and judgements that are explicitly recorded.

## Purpose

Use this policy to answer four practical questions:

1. Are requested outcomes being completed successfully?
2. How much retry pressure was required?
3. What failure modes keep repeating?
4. What known cost was spent?

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

To choose between `product` and `meta`: ask whether the change expands what a user of the tool can do. If yes, use `product`. If the work is internal overhead — tracking, auditing, policy updates, or fixing bookkeeping — use `meta`. Examples: new CLI command or ingest adapter → `product`; updating this policy doc or fixing a metrics tracking bug → `meta`.

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

- source of truth: `metrics/events.ndjson` (append-only event log; tracked in git)
- optional export: `docs/ai-agents-metrics.md`

If they disagree, the event log wins.

Do not edit `metrics/events.ndjson` manually. All mutations must go through the CLI.

## Required Workflow

### At Goal Start

1. Detect whether the work belongs to an existing goal or a new goal.
2. Create a new goal if needed.
3. Set status to `in_progress`.
4. Initialize attempts to `0`.
5. Do this before substantial implementation, documentation, or validation work begins.

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

### History extraction (primary flow)

```bash
ai-agents-metrics history-update                   # reads ~/.codex (Codex)
ai-agents-metrics history-update --source claude   # reads ~/.claude (Claude Code)
ai-agents-metrics show
ai-agents-metrics history-compare
```

### Manual tracking (opt-in)

```bash
ai-agents-metrics start-task --title "Add CSV import" --task-type product
ai-agents-metrics continue-task --task-id <goal-id> --notes "Retry after review"
ai-agents-metrics finish-task --task-id <goal-id> --status success --notes "Validated"
ai-agents-metrics ensure-active-task
ai-agents-metrics sync-usage
ai-agents-metrics render-report
```

The public workflow contract should stay agent-agnostic. Provider-specific detection and telemetry support belong behind internal adapters, not in required public CLI flags.

Automatic local usage sync is implemented for Codex telemetry (SQLite) and Claude Code telemetry (JSONL under `~/.claude/projects/`). Both are detected automatically — no provider-specific flag is required. Additional agents remain in scope for the product and should land through the same universal command surface.

When repository work has already started but no active task exists yet, prefer `ai-agents-metrics ensure-active-task` before continuing with active-work commands.

If `ai-agents-metrics` is expected but unavailable, treat that as an `environment_issue` or installation mismatch and report it clearly.

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

### `show` command and history signals

`ai-agents-metrics show` prints the current ledger summary. Pass `--json` to get a machine-readable JSON object.

When a history warehouse is available (auto-detected by default; override with `--warehouse-path`), `show --json` includes a top-level `history_signals` key:

```json
{
  "history_signals": {
    "project_threads": 72,
    "retry_threads": 21,
    "retry_rate": 0.29,
    "ledger_goal_alignments": 8,
    "ledger_goals_total": 14
  }
}
```

When no warehouse is available or the warehouse has not been derived yet, `history_signals` is `null`. Consumers must handle both cases.

- `project_threads` — total history threads attributed to this project (worktrees merged into parent).
- `retry_threads` — threads that had more than one session (direct proxy for retry pressure).
- `retry_rate` — `retry_threads / project_threads`; the primary history-derived efficiency signal.
- `ledger_goal_alignments` — how many closed ledger goals with timestamps have at least one matching history thread in their time window.
- `ledger_goals_total` — denominator for the alignment ratio.

Use `retry_rate` from `history_signals` as the authoritative retry-pressure signal. The ledger's own `attempts_per_closed_task` field is a weaker proxy because retries at the conversation level are often not captured in structured attempt records.

## Anti-Gaming Rules

- Do not split one coherent goal into many tiny goals to inflate success rate.
- Do not classify bookkeeping or retrospective work as product delivery.
- Do not keep failed work as `in_progress` forever to hide failure.
- Do not mark a goal as success before validation is complete.
