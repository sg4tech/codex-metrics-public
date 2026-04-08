# ARCH-004: Remove hidden transformation from save_metrics

**Priority:** medium
**Complexity:** low
**Status:** obsolete — `save_metrics` was removed in CODEX-50 (NDJSON event store migration); storage.py is now a pure I/O layer with no business-logic transforms

## Problem

`storage.save_metrics` silently removes the `tasks` key on every write:

```python
def save_metrics(path: Path, data: dict[str, Any]) -> None:
    with metrics_file_immutability_guard(path):
        data_to_save = dict(data)
        data_to_save.pop("tasks", None)   # ← unexpected in an I/O function
        serialized = json.dumps(data_to_save, ...)
```

`storage.py` is an I/O layer. It should not know about the business schema. If another key with similar legacy semantics appears, it is not obvious that it also needs to be excluded here. This violates the principle of least surprise.

## Desired state

**Option A (preferred):** move `pop("tasks", ...)` to the call site, where it is an explicit, intentional choice. `save_metrics` writes exactly what it receives.

**Option B:** introduce a `MetricsData` type (TypedDict or dataclass) instead of `dict[str, Any]` — then the `tasks` field simply does not exist in the schema and the question goes away entirely.

## Acceptance criteria

- [ ] `save_metrics` contains no business-logic transformations
- [ ] What gets written to the file is visible at the call site
- [ ] `make verify` passes
