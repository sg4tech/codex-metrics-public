# ARCH-001: Remove re-exports from cli.py

**Priority:** high
**Complexity:** low
**Status:** closed

## Problem

`cli.py` does two incompatible things: it is the CLI entry point and it re-exports ~50 symbols from `domain`, `reporting`, and `storage`:

```python
# cli.py lines 88-196 — re-export facade
build_operator_review = reporting.build_operator_review
GoalRecord = domain.GoalRecord
save_metrics = storage.save_metrics
validate_goal_record = domain.validate_goal_record
# ... 45+ more lines
```

Tests and scripts that import from `cli` pull the entire CLI layer as a dependency — argparse, subprocess, sqlite3. Adding any new function to `domain` requires updating the re-export list in `cli.py`.

## Desired state

- External code imports directly: `from codex_metrics.domain import GoalRecord`
- `cli.py` contains only: argparse definitions, command handler functions, `console_main`
- If backward compatibility is needed, keep the shim with explicit `# deprecated re-export` comments — not silently

## Acceptance criteria

- [x] No re-exports in `cli.py` (or all remaining ones are marked deprecated)
- [x] All tests import from the correct module
- [x] `make verify` passes
