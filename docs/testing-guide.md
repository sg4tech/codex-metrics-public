# Testing Guide

How tests are structured, what `conftest.py` provides, and how to write new tests in this project.

---

## Running tests

```bash
make verify          # lint + typecheck + tests (canonical entry point)
make test            # pytest only
make lint            # ruff only
make typecheck       # mypy only
python -m pytest tests/test_workflow_fsm.py -v   # single file
```

Configuration in `pyproject.toml`:
- `pythonpath = ["src"]` — package path is pre-configured; no need to set `PYTHONPATH=src` manually
- Coverage: branch mode, parallel, source = `codex_metrics`

---

## Structure: one file per module

| Test file | Covers |
|-----------|--------|
| `test_update_codex_metrics.py` | CLI end-to-end via subprocess |
| `test_update_codex_metrics_domain.py` | Domain logic (unit) |
| `test_workflow_fsm.py` | State machine transitions |
| `test_history_{ingest,normalize,derive,compare,audit}.py` | Pipeline stages |
| `test_storage_{roundtrip,immutability}.py` | File I/O and lockfiles |
| `test_{cost_audit,reporting,retro_timeline}.py` | Analysis and reporting |
| `test_{git_hooks,commit_message,public_boundary}.py` | Integrations |
| `test_observability.py` | Event store |
| `test_public_overlay.py` | Public/private sync |
| `test_export_public_tree.py` | Export logic |
| `test_claude_md.py` | Documentation generation |

---

## conftest.py

`conftest.py` is empty (only the `from __future__ import annotations` header). No shared fixtures are needed at the top level.

The former `unlock_tmp_path_immutability` autouse fixture was removed when the OS-level immutability guard (`chflags uchg`) was replaced by the append-only event log. `tmp_path` cleanup now works without intervention.

---

## Two test styles

### 1. Unit tests via direct import

For domain logic, FSM, reporting, and other pure modules.

```python
from codex_metrics.workflow_fsm import classify_workflow_state, WorkflowState

def test_active_goal_detected() -> None:
    state = classify_workflow_state(
        active_goal_count=1,
        started_work_detected=True,
        git_available=True,
    )
    assert state == WorkflowState.ACTIVE_GOAL_EXISTS
```

`@pytest.mark.parametrize` is the standard pattern for FSM and validation tests:

```python
@pytest.mark.parametrize(("input", "expected"), [
    ("success", True),
    ("fail", False),
])
def test_something(input: str, expected: bool) -> None:
    ...
```

### 2. End-to-end tests via subprocess

For CLI commands. Use `tmp_path` as an isolated repo root.

Helper functions defined in `test_update_codex_metrics.py` (reused across test files):

```python
# Run via legacy script
def run_cmd(tmp_path: Path, *args: str, extra_env=None) -> subprocess.CompletedProcess[str]:
    ...

# Run via python -m codex_metrics (primary path)
def run_module_cmd(tmp_path: Path, *args: str, extra_env=None) -> subprocess.CompletedProcess[str]:
    ...
```

End-to-end test pattern:

```python
def test_start_and_finish(tmp_path: Path) -> None:
    result = run_module_cmd(tmp_path, "init")
    assert result.returncode == 0

    result = run_module_cmd(tmp_path, "start-task", "--title", "My task", "--type", "product")
    assert result.returncode == 0

    metrics_path = tmp_path / "metrics" / "codex_metrics.json"
    data = json.loads(metrics_path.read_text())
    goals = data["goals"]
    assert len(goals) == 1
    assert goals[0]["status"] == "in_progress"
```

---

## Object factories

`test_update_codex_metrics_domain.py` defines factory functions with defaults and `**overrides`. They live locally in that file, not in `conftest.py`. Copy the pattern when needed:

```python
def make_goal_dict(**overrides: object) -> dict[str, object]:
    values = {
        "goal_id": "goal-1",
        "title": "Goal",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "in_progress",
        "attempts": 0,
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
        "result_fit": None,
    }
    values.update(overrides)
    return values

# Usage — only override what matters for the test:
goal = make_goal_dict(status="fail", failure_reason="unclear_task", attempts=1)
```

The same pattern exists for `make_goal_record`, `make_effective_goal_record`, and `make_attempt_entry_record` — dataclass versions of the same objects.

---

## Testing with SQLite (history pipeline)

Tests for `history_ingest` / `history_normalize` / `history_derive` require creating SQLite databases with the correct schema.

`create_codex_usage_sources(repo, ...)` in `test_update_codex_metrics.py` creates:
- `codex_state.sqlite` with a `threads` table
- `codex_logs.sqlite` with a `logs` table

This is a test double for the real `~/.codex/state_5.sqlite` and `~/.codex/logs_1.sqlite`. Usage pattern:

```python
def test_ingest(tmp_path: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(
        tmp_path,
        thread_id="thread-abc",
        model="gpt-5",
        input_tokens=1000,
    )
    summary = ingest_codex_history(
        source_root=tmp_path,
        warehouse_path=tmp_path / "warehouse.sqlite",
    )
    assert summary.threads_ingested == 1
```

---

## Three required buckets for mutating commands

From `AGENTS.md` — for `update`, `merge-tasks`, and sync flows:

1. **Happy path** — successful execution; verify file state after the call
2. **Invalid-state rejection** — command must exit with a non-zero return code
3. **Summary/report consistency** — after mutation, `summary` in the JSON is consistent with `goals`/`entries`

```python
def test_update_happy_path(tmp_path): ...
def test_update_rejects_closed_goal(tmp_path): ...
def test_update_summary_stays_consistent(tmp_path): ...
```

---

## Coverage with subprocess

Tests that invoke the CLI via `subprocess` are not covered by default.
To enable: `CODEX_SUBPROCESS_COVERAGE=1 make test`.
`build_cmd` and `run_module_cmd` automatically switch to `coverage run --parallel-mode`.

---

## Common pitfalls

**Immutability blocking the test:**
The `unlock_tmp_path_immutability` fixture handles this automatically. If it doesn't, verify that the file is created inside `tmp_path`, not alongside it.

**PYTHONPATH in a worktree:**
`.venv` is a symlink to the main repo. In a worktree, always use `PYTHONPATH=src` or run via `make`.

**Test mutating the real `metrics/codex_metrics.json`:**
CLI commands in end-to-end tests must be run with `cwd=tmp_path`. This makes them resolve `metrics/codex_metrics.json` relative to `tmp_path`, not the actual repository.
