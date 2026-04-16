# ARCH-016: Propagate model to all derived tables

**Priority:** medium
**Complexity:** low
**Status:** planned

## Problem

`model` is reliably available in `normalized_usage_events` (52/52 rows populated) and `derived_message_facts`, but does not reach the higher-level derived tables:

| Table | `model` column | Populated? |
|---|---|---|
| `normalized_usage_events` | yes | yes — always filled |
| `derived_message_facts` | yes | yes — always filled |
| `derived_session_usage` | **no** | — |
| `derived_attempts` | **no** (has `model_provider`) | — |
| `derived_goals` | yes | **always NULL** |
| `derived_projects` | **no** | — |

This means any consumer that needs model + tokens (cost calculation, model-aware analysis, export) must join back to `normalized_usage_events` or `derived_message_facts` — defeating the purpose of pre-aggregated derived tables.

## Proposed solution

Propagate `model` during the derive step:

1. **`derived_session_usage`** — add `model TEXT` column. Populate from `normalized_usage_events` grouped by `session_path`. If a session uses multiple models, pick the dominant one (highest `usage_event_count`).

2. **`derived_attempts`** — add `model TEXT` column alongside existing `model_provider`. Same logic: dominant model from usage events for that session.

3. **`derived_goals`** — already has the column, just never populated. Set to dominant model across all sessions for the thread. If mixed, store the most-used one.

4. **`derived_projects`** — consider adding `models TEXT` (JSON array of distinct models seen). Lower priority.

## Migration

- `ALTER TABLE derived_session_usage ADD COLUMN model TEXT` (same pattern already used for `cache_creation_input_tokens`)
- `ALTER TABLE derived_attempts ADD COLUMN model TEXT`
- `derived_goals.model` — no schema change needed, just populate during derive
- Re-derive populates all rows; no backfill script needed

## Validation

- After re-derive: `SELECT count(*) FROM derived_session_usage WHERE model IS NULL` should be 0 for sessions with usage events
- `derived_goals.model` should match the model seen in `derived_message_facts` for the same thread
- Existing tests should pass unchanged (model is additive)

## Relationship

- Prerequisite for warehouse export (H-039)
- Closes the gap identified in H-013 (model tracking validated but not fully propagated to warehouse)
- Enables cost calculation directly from derived tables without joins to normalized layer
