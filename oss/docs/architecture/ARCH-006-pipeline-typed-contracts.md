# ARCH-006: Add typed contracts between pipeline stages

**Priority:** medium
**Complexity:** medium
**Status:** done

## Problem

The `ingest → normalize → derive` pipeline passes data through SQLite. The schema between stages exists only in column names and SQL queries — not in Python types:

```
history_ingest.py    → SQLite (raw)        → history_normalize.py
history_normalize.py → SQLite (normalized) → history_derive.py
history_derive.py    → GoalRecord / AttemptEntryRecord
```

If `normalize` renames a column, `derive` will raise a `KeyError` at runtime. mypy cannot catch this. Adding a new field in one stage is not reflected in the next stage's signature.

## Desired state

Add `TypedDict` (or dataclasses) for rows at stage boundaries:

```python
# history_normalize.py
class NormalizedMessageRow(TypedDict):
    session_id: str
    message_id: str
    role: str
    timestamp: str | None
    ...

# history_derive.py accepts Iterable[NormalizedMessageRow]
```

SQLite remains the storage medium, but Python types serve as a documented contract. Schema mismatches become visible at type-check time rather than at runtime.

## Acceptance criteria

- [ ] A TypedDict or dataclass is defined for each stage boundary
- [ ] `history_normalize.py` and `history_derive.py` use these types in function signatures
- [ ] mypy passes without new `# type: ignore` suppressions
- [ ] `make verify` passes

## Notes

- Start with the normalize→derive boundary — it is the most active and complex
- The ingest→normalize boundary can be done in a second iteration
