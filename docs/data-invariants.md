# Data Invariants

Business rules that must always hold for data in `metrics/events.ndjson` and the replayed in-memory state.

These are enforced by `validate_task_business_rules` and `validate_entry_business_rules` in `domain.py`. This document is a human-readable summary — keep it in sync when changing validation logic.

---

## GoalRecord

### Status rules
- `status=fail` → `failure_reason` is required (non-null)
- `status=success` → `failure_reason` must be `null`
- `status in {success, fail}` → `attempts >= 1` (closed goals must have at least one attempt)
- `status=in_progress` → `finished_at` must be `null`
- `status=in_progress` → `result_fit` must be `null`

### Timestamp rules
- `finished_at` cannot be earlier than `started_at` when both are present
- All timestamps must include a timezone offset (bare local times are rejected)
- **Storage format:** ISO 8601 string (`"2026-04-06T10:00:00+00:00"`) in `events.ndjson`
- **In-memory type:** `datetime | None` in `GoalRecord` / `AttemptEntryRecord` / `EffectiveGoalRecord`
- String ↔ datetime conversion happens only in `domain/serde.py` (`_parse_ts` / `_dump_ts`). Do not call `parse_iso_datetime_flexible` outside the serde layer for goal/entry timestamps.

### result_fit rules
- `result_fit` is only allowed when `goal_type=product`
- `status=success` → `result_fit != "miss"`
- `status=fail` → `result_fit` must be `null` or `"miss"`

### Token rules
- When all four token fields are present: `tokens_total >= input_tokens + cached_input_tokens + output_tokens`
  (the difference covers reasoning/tool tokens not broken down separately)
- All token counts must be non-negative
- `cost_usd` must be non-negative

### Field value constraints
- `goal_type` ∈ `{product, retro, meta}`
- `status` ∈ `{in_progress, success, fail}`
- `failure_reason` ∈ `{unclear_task, missing_context, validation_failed, environment_issue, model_mistake, scope_too_large, tooling_issue, other}`
- `result_fit` ∈ `{exact_fit, partial_fit, miss}`
- `agent_name` must not be an empty string (null is allowed)
- `model` must not be an empty string (null is allowed)

---

## AttemptEntryRecord

### Status rules
- `status=fail` and `inferred=false` → `failure_reason` is required
- `status=fail` and `inferred=true` → `failure_reason` may be `null` (inferred entries have incomplete data)
- `status=success` → `failure_reason` must be `null`
- `status=in_progress` → `finished_at` must be `null`

### Timestamp rules
- `finished_at` cannot be earlier than `started_at` when both are present
- All timestamps must include a timezone offset
- Same storage/in-memory type rules as `GoalRecord` (see above)

### Token rules
- Same as GoalRecord: `tokens_total >= input + cached + output` when all four are present
- All token counts and `cost_usd` must be non-negative

---

## Cross-record rules

- Every `entry.goal_id` must reference an existing `GoalRecord.goal_id`
- `entry_id` format: `{goal_id}-attempt-{NNN}` (three digits, zero-padded)
- `goal_id` format: `YYYY-MM-DD-NNN` (three digits, zero-padded)
- `supersedes_goal_id` must reference an existing `goal_id` when non-null

---

## Summary block

- Computed automatically during replay; never edited manually
- `success_rate` and `attempts_per_closed_task` are `null` when `closed_tasks = 0`
- `cost_per_success_usd` is `null` unless cost data is available for all successes
