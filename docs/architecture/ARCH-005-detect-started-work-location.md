# ARCH-005: Move detect_started_work out of cli.py

**Priority:** medium
**Complexity:** low
**Status:** done

## Problem

Business logic for determining "has work been started in the repository" lives in `cli.py`:

```python
# cli.py lines 259-325
MEANINGFUL_WORKTREE_DIRS = {"src", "tests", "docs", "scripts", "tools"}
MEANINGFUL_WORKTREE_FILES = {"AGENTS.md", "README.md", "Makefile", "pyproject.toml"}
LOW_SIGNAL_WORKTREE_PATHS = {Path("metrics/codex_metrics.json"), ...}

def detect_started_work(cwd: Path) -> StartedWorkReport: ...
def _is_meaningful_worktree_path(path_text: str) -> bool: ...
```

This logic feeds directly into `workflow_fsm.py` — it is part of the FSM, not the CLI. As a result, `workflow_fsm` cannot be fully tested without importing the CLI layer.

## Desired state

Move to `workflow_fsm.py` (or a separate `git_state.py` if the file becomes too large):
- `StartedWorkReport`
- `detect_started_work`
- `_is_meaningful_worktree_path`
- `MEANINGFUL_WORKTREE_DIRS`, `MEANINGFUL_WORKTREE_FILES`, `LOW_SIGNAL_WORKTREE_PATHS`

`cli.py` calls `detect_started_work` via an import from the new location.

## Acceptance criteria

- [ ] `detect_started_work` is not defined in `cli.py`
- [ ] `test_workflow_fsm.py` can test the full state-detection cycle without importing from `cli`
- [ ] `make verify` passes
