# Data Schema

**What this document is:** The full field reference for the in-memory data model — `GoalRecord`, `AttemptEntryRecord`, and the `summary` block.

**When to read this:**
- Writing code that reads or writes goal/entry data
- Debugging an unexpected field value or validation error
- Understanding what a specific field means

**Related docs:**
- [data-invariants.md](data-invariants.md) — business rules that must hold for all records
- [architecture.md](architecture.md) — how storage and replay work
- [docs/glossary.md](glossary.md) — terminology: goal vs task, entry vs attempt, supersedes chain, etc.

---

## Summary

The primary store is `metrics/events.ndjson` — an append-only NDJSON event log. The in-memory state is reconstructed by replaying events at read time. The three top-level keys are `goals`, `entries`, and `summary`.

- `goals` — list of `GoalRecord` objects (one per tracked task)
- `entries` — list of `AttemptEntryRecord` objects (one per attempt within a goal)
- `summary` — aggregated statistics; always computed in-memory, never stored

---

## Core concepts

- **Goal** — the unit of tracked work. One goal per task or retrospective. See `GoalRecord`.
- **Entry (attempt)** — one implementation pass within a goal. A goal with `attempts=2` has two entries. See `AttemptEntryRecord`.
- **Event log** — `metrics/events.ndjson`: append-only, one JSON line per CLI command. State is reconstructed at read time via last-write-wins replay.

---

## Source of truth

- `metrics/events.ndjson` is the canonical store. All other representations are derived.
- The `summary` block is always recomputed in-memory on `load_metrics`. Do not edit it manually.
- The `tasks` key is a legacy alias for `goals`. It is normalised to `goals` in-memory during replay and never written to `events.ndjson`.

---

## Top-level structure

```json
{
  "summary": { ... },
  "goals": [ ... ],
  "entries": [ ... ]
}
```

| Key | Type | Description |
|-----|------|-------------|
| `summary` | object | Aggregated statistics. Computed in-memory on every `load_metrics` call; never stored in `events.ndjson`. |
| `goals` | array | List of `GoalRecord` objects in chronological order. |
| `entries` | array | List of `AttemptEntryRecord` objects — one per attempt within a goal. |

> The `tasks` key is a legacy alias for `goals`. It is normalised to `goals` in-memory during event replay and is never stored in `events.ndjson`.

---

## GoalRecord

One task (goal). Corresponds to a Linear issue or a retrospective.

```json
{
  "goal_id": "2026-04-06-001",
  "title": "Add public boundary verification",
  "goal_type": "product",
  "supersedes_goal_id": null,
  "status": "success",
  "attempts": 2,
  "started_at": "2026-04-06T10:00:00+00:00",
  "finished_at": "2026-04-06T11:30:00+00:00",
  "cost_usd": 1.234567,
  "input_tokens": 12000,
  "cached_input_tokens": 340000,
  "output_tokens": 4500,
  "tokens_total": 980000,
  "failure_reason": null,
  "notes": "Implemented and tested. Pre-push hook integration verified.",
  "result_fit": "exact_fit",
  "agent_name": null,
  "model": "gpt-5.4-mini"
}
```

### GoalRecord fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal_id` | string | ✓ | Unique ID in `YYYY-MM-DD-NNN` format (three digits, zero-padded) |
| `title` | string | ✓ | Short task description |
| `goal_type` | string | ✓ | One of: `product` / `retro` / `meta` |
| `supersedes_goal_id` | string\|null | | ID of the goal this one replaces (used in retry chains) |
| `status` | string | ✓ | One of: `in_progress` / `success` / `fail` |
| `attempts` | int | ✓ | Number of attempts. `0` if never closed. Closed goals require at least `1`. |
| `started_at` | string\|null | | ISO 8601 with timezone. Example: `2026-04-06T10:00:00+00:00`. In-memory Python type: `datetime \| None` (parsed by `serde.py`). |
| `finished_at` | string\|null | | ISO 8601 with timezone. Must be `null` when `status=in_progress`. In-memory Python type: `datetime \| None`. |
| `cost_usd` | float\|null | | Cost in USD. `null` means no data available. |
| `input_tokens` | int\|null | | Non-cached input tokens. `null` means no data. |
| `cached_input_tokens` | int\|null | | Tokens served from cache. `null` means no data. |
| `output_tokens` | int\|null | | Output tokens. `null` means no data. |
| `tokens_total` | int\|null | | Total tokens (may include reasoning tokens). `null` means no data. |
| `failure_reason` | string\|null | | Required when `status=fail`. See allowed values below. |
| `notes` | string\|null | | Free text. What was done, relevant context. |
| `result_fit` | string\|null | | Only for `goal_type=product`. One of: `exact_fit` / `partial_fit` / `miss` |
| `agent_name` | string\|null | | Name of the agent that executed the task. |
| `model` | string\|null | | Model name. Examples: `gpt-5.4-mini`, `claude-sonnet-4-6` |

### Allowed values

**`goal_type`:** `product`, `retro`, `meta`

**`status`:** `in_progress`, `success`, `fail`

**`failure_reason`** (required when `status=fail`):
- `unclear_task` — task was not clearly defined
- `missing_context` — insufficient context to complete the task
- `validation_failed` — result did not pass validation
- `environment_issue` — problem with the environment or tooling setup
- `model_mistake` — error made by the model
- `scope_too_large` — task turned out to be too large for a single attempt
- `tooling_issue` — problem with the tooling itself
- `other`

**`result_fit`** (only for `goal_type=product`):
- `exact_fit` — result fully matches expectations
- `partial_fit` — result partially matches expectations
- `miss` — result was not accepted

---

## AttemptEntryRecord

One attempt within a goal. A goal with `attempts=2` has two records in `entries`.

```json
{
  "entry_id": "2026-04-06-001-attempt-001",
  "goal_id": "2026-04-06-001",
  "entry_type": "product",
  "inferred": false,
  "status": "fail",
  "started_at": "2026-04-06T10:00:00+00:00",
  "finished_at": "2026-04-06T10:45:00+00:00",
  "cost_usd": 0.456789,
  "input_tokens": 5000,
  "cached_input_tokens": 120000,
  "output_tokens": 1800,
  "tokens_total": 400000,
  "failure_reason": "validation_failed",
  "notes": null,
  "agent_name": null,
  "model": "gpt-5.4-mini"
}
```

### AttemptEntryRecord fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `entry_id` | string | ✓ | Format: `{goal_id}-attempt-{NNN}` |
| `goal_id` | string | ✓ | Reference to the parent `GoalRecord.goal_id` |
| `entry_type` | string | ✓ | Attempt type. Typically matches the parent goal's `goal_type`. |
| `inferred` | bool | ✓ | `true` if the record was created automatically during history reconstruction |
| `status` | string | ✓ | One of: `in_progress` / `success` / `fail` |
| `started_at` | string\|null | | ISO 8601 with timezone |
| `finished_at` | string\|null | | ISO 8601 with timezone. `null` when `status=in_progress`. |
| `cost_usd` | float\|null | | Cost of this attempt |
| `input_tokens` | int\|null | | |
| `cached_input_tokens` | int\|null | | |
| `output_tokens` | int\|null | | |
| `tokens_total` | int\|null | | |
| `failure_reason` | string\|null | | Required when `status=fail` and `inferred=false` |
| `notes` | string\|null | | |
| `agent_name` | string\|null | | |
| `model` | string\|null | | |

---

## summary (aggregate)

Recomputed automatically on every `load_metrics` call. Do not edit manually.

### Top-level summary fields

| Field | Description |
|-------|-------------|
| `closed_tasks` | Number of goals with `status=success` or `fail` |
| `successes` / `fails` | Breakdown by outcome |
| `total_attempts` | Sum of `attempts` across all goals |
| `total_cost_usd` | Total cost |
| `total_input_tokens` / `total_cached_input_tokens` / `total_output_tokens` / `total_tokens` | Summed token counts |
| `success_rate` | `successes / closed_tasks`. `null` if no closed goals. |
| `attempts_per_closed_task` | `total_attempts / closed_tasks`. `null` if no closed goals. |
| `known_cost_successes` | Number of successful goals that have cost data |
| `known_cost_per_success_usd` | Average cost per success based on known data |
| `complete_cost_per_covered_success_usd` | Same, but only goals with complete data |
| `cost_per_success_usd` | Average cost across all successes. `null` if any data is missing. |
| `model_summary_goals` | Number of goals with model data |
| `model_complete_goals` | Number of goals where all attempts used the same model |
| `mixed_model_goals` | Number of goals where attempts used different models |

### Nested summary blocks

| Key | Description |
|-----|-------------|
| `by_goal_type` | Same metrics broken down by `meta`, `product`, `retro` |
| `by_task_type` | Legacy alias for `by_goal_type` |
| `by_model` | Same metrics grouped by model name |
| `entries` | Aggregate over `AttemptEntryRecord` (not goals): `closed_entries`, `success_rate`, `failure_reasons`, tokens |

---

## Formats and constraints

**ID format:**
- `goal_id`: `YYYY-MM-DD-NNN` — creation date + sequence number for that day (001, 002, ...)
- `entry_id`: `{goal_id}-attempt-NNN`

**Timestamps:** ISO 8601, always with timezone (`+00:00` or `Z`). No microseconds.

**Tokens:** `tokens_total` may exceed `input + cached + output` — the difference is reasoning/tool tokens not broken down separately. When all four fields are present: `tokens_total >= input + cached + output`.

**Cost:** rounded to 6 decimal places via `round_usd`.

> For the full set of validation rules that apply to these fields, see [data-invariants.md](data-invariants.md).

---

## Warehouse: derived_projects token coverage columns

The `derived_projects` table (Layer 4 aggregate in the history warehouse) holds per-project rollups of session token counts. Because some sessions have no usage events at all, raw token sums must be accompanied by coverage denominators so consumers can distinguish "zero tokens" from "no data".

| Column | Type | Description |
|--------|------|-------------|
| `input_tokens` | INTEGER \| NULL | Sum of input tokens across sessions that had usage data. NULL if no sessions had usage data. |
| `output_tokens` | INTEGER \| NULL | Sum of output tokens across covered sessions. NULL if uncovered. |
| `total_tokens` | INTEGER \| NULL | Sum of total tokens across covered sessions. NULL if uncovered. |
| `input_tokens_covered_sessions` | INTEGER | Count of sessions that contributed a non-NULL `input_tokens` sum. 0 if no session had usage data. |
| `output_tokens_covered_sessions` | INTEGER | Count of sessions that contributed a non-NULL `output_tokens` sum. |
| `total_tokens_covered_sessions` | INTEGER | Count of sessions that contributed a non-NULL `total_tokens` sum. |

**Usage pattern:** To compute a meaningful per-session token average, use `total_tokens / total_tokens_covered_sessions` rather than `total_tokens / attempt_count`. Sessions without usage data are excluded from both the numerator and denominator.

**raw_json:** All six fields above are included in `derived_projects.raw_json` for downstream consumers that do not query the warehouse directly.
