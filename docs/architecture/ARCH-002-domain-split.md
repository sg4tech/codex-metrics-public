# ARCH-002: Split domain.py into layers

**Priority:** high
**Complexity:** medium
**Status:** done

## Problem

`domain.py` is a monolith that contains all of the following at once:
- dataclass models (`GoalRecord`, `AttemptEntryRecord`, `EffectiveGoalRecord`)
- serialisation (`goal_from_dict`, `goal_to_dict`, `entry_from_dict`, ...)
- validation (`validate_goal_record`, `validate_entry_record`, `validate_metrics_data`, ...)
- aggregation (`aggregate_chain_costs`, `compute_summary_block`, `build_effective_goals`, ...)
- timestamp helpers (`now_utc_iso`, `parse_iso_datetime`, ...)
- ID generation (`next_goal_id`, `next_entry_id`)
- legacy migration (`LEGACY_GOAL_SUPERSEDES_MAP`, `normalize_legacy_metrics_data`)

Any change to any of these layers touches the same file.

## Desired state

Split into submodules:

```
src/codex_metrics/domain/
    __init__.py        # re-exports the public API (backward compatibility)
    models.py          # dataclasses only
    serde.py           # from_dict / to_dict
    validation.py      # validate_* functions
    aggregation.py     # aggregate_*, compute_summary_block, build_effective_goals
    ids.py             # next_goal_id, next_entry_id
    time_utils.py      # now_utc_iso, parse_iso_datetime, ...
```

`domain/__init__.py` re-exports everything — the external API does not break.

## Acceptance criteria

- [x] `from codex_metrics.domain import GoalRecord` continues to work
- [x] All tests pass without changing imports
- [x] Each submodule imports only what it needs (no cross-module cycles)
- [x] `make verify` passes

## Notes

- Do this incrementally, one submodule at a time
- Start with `models.py` — it has no dependencies on other parts of domain
- Leave `aggregation.py` for last — it has the most complex dependency graph
