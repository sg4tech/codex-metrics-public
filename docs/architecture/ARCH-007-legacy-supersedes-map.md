# ARCH-007: Remove hardcoded LEGACY_GOAL_SUPERSEDES_MAP from domain.py

**Priority:** low
**Complexity:** low
**Status:** done

## Problem

`domain.py` contains hardcoded goal IDs specific to this repository:

```python
LEGACY_GOAL_SUPERSEDES_MAP = {
    "2026-03-29-008": "2026-03-29-007",
}
```

This is project-specific data baked into business logic. `domain.py` is no longer portable — it depends on the history of one project. Any future legacy fix requires a code change.

## Desired state

Choose one option:

**A. Delete** — if this migration has already been applied and the data in `codex_metrics.json` is correct, the map is no longer needed. Remove it along with `normalize_legacy_metrics_data`, or keep the function but have it accept the map as a parameter.

**B. Move to config** — add an optional `legacy_supersedes` field to `codex_metrics.json` or a separate `metrics/legacy_migrations.json` file. `domain.py` reads it on load.

## Resolution

Chose **Option A (delete)**. Confirmed that the migration was already applied: goal IDs `2026-03-29-008` and `2026-03-29-007` are absent from `metrics/events.ndjson`. The constant and its two usage lines inside `normalize_legacy_metrics_data` were removed. The function itself was kept — it handles the broader `tasks → goals` schema migration and field normalization, which remain relevant for loading legacy JSON snapshots.

## Acceptance criteria

- [x] `LEGACY_GOAL_SUPERSEDES_MAP` is not a module-level constant in `domain.py`
- [x] Option A chosen — no config path needed
- [x] `make verify` passes (348 tests, ruff, mypy, security scan)
