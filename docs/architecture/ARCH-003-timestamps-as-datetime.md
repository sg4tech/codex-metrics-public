# ARCH-003: Store timestamps as datetime in dataclasses

**Priority:** medium
**Complexity:** medium
**Status:** done

## Problem

`GoalRecord` and `AttemptEntryRecord` store timestamps as strings:

```python
@dataclass
class GoalRecord:
    started_at: str | None
    finished_at: str | None
```

Consequences:
- Parsing (`parse_iso_datetime`, `parse_iso_datetime_flexible`) is scattered throughout the codebase
- Two separate parsing functions exist instead of one — because the input format is not normalised at the boundary
- Timezone errors surface at runtime; mypy cannot catch them
- Date arithmetic requires parsing first rather than using native datetime operations

## Desired state

- Inside dataclasses: `started_at: datetime | None`
- String → datetime conversion happens only in `serde.py` when reading from JSON
- datetime → string conversion happens only in `serde.py` when writing to JSON
- All domain and aggregation code uses native `datetime` operations

## Acceptance criteria

- [x] `GoalRecord.started_at` and `finished_at` are typed as `datetime | None`
- [x] Same for `AttemptEntryRecord` and `EffectiveGoalRecord`
- [x] `parse_iso_datetime_flexible` consolidated to the serde boundary (`serde.py` + entry points in `aggregation.py`)
- [x] mypy passes without new `# type: ignore` suppressions on datetime code
- [x] `make verify` passes (304/304)

## Notes

- Best done after ARCH-002 (dedicated serde.py needed); otherwise changes scatter across all of domain.py
- Audit all places where `started_at` flows into JSON output — each will need `.isoformat()`
