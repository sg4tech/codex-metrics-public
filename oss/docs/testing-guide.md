# Testing Guide

**What this document is:** How tests are structured, what helpers are available, and how to write new tests correctly.

**When to read this:**
- Writing a new test or adding coverage to an existing module
- Debugging a test failure and not sure why it is behaving unexpectedly
- Setting up a new worktree or environment and need to run tests

**Related docs:**
- [architecture.md](architecture.md) — what each module does and where it lives
- [data-schema.md](data-schema.md) — shape of the data used in test fixtures

---

## Summary

Tests are split into two styles: unit tests (direct import) and CLI integration tests (in-process by default, subprocess for coverage mode). The canonical entry points are `make verify-fast` and `make verify` (both are final-gate commands before committing — not intermediate diagnostic tools). Every mutating command should have three test buckets: happy path, invalid-state rejection, and summary consistency.

---

## Quick start

```bash
make verify-fast     # lint + typecheck + tests (~55s) — final gate before commit
make verify          # full suite incl. bandit, pylint, complexity (~1.5min) — before committing
make test            # pytest only
make lint            # ruff only
make typecheck       # mypy only
python -m pytest tests/workflow/test_workflow_fsm.py -v   # single file
```

Configuration in `pyproject.toml`:
- `pythonpath = ["src"]` — package path is pre-configured; no need to set `PYTHONPATH=src` manually
- Coverage: branch mode, parallel, source = `ai_agents_metrics`

---

## Common workflows

**Before a commit:**
```bash
make verify
```

**Debugging a single test:**
```bash
python -m pytest tests/cli/test_metrics_cli.py::test_name -v -s
```

**Running with subprocess coverage enabled:**
```bash
CODEX_SUBPROCESS_COVERAGE=1 make test
```

---

## Structure: one file per module

| Test file | Covers |
|-----------|--------|
| `test_metrics_cli.py` | CLI integration (in-process, subprocess for a few tests) |
| `test_metrics_domain.py` | Domain logic (unit) |
| `test_workflow_fsm.py` | State machine transitions |
| `test_history_{ingest,normalize,derive,compare,audit}.py` | Pipeline stages |
| `test_storage_roundtrip.py` | Event log I/O and replay |
| `test_{cost_audit,reporting,retro_timeline}.py` | Analysis and reporting |
| `test_{git_hooks,commit_message,public_boundary}.py` | Integrations |
| `test_observability.py` | Event store |
| `test_public_overlay.py` | Public/private sync |
| `test_claude_md.py` | Documentation generation |

---

## conftest.py

`conftest.py` provides `run_cli_inprocess()` — an in-process CLI runner that calls `main()` directly with captured stdout/stderr and temporary `os.chdir()`. This eliminates Python startup overhead (~0.5s per subprocess call) and makes tests ~18x faster than the previous subprocess-based approach.

Tests use `run_cli_inprocess()` by default and fall back to real subprocess when `CODEX_SUBPROCESS_COVERAGE=1` is set.

---

## Two test styles

### 1. Unit tests via direct import

For domain logic, FSM, reporting, and other pure modules.

```python
from ai_agents_metrics.workflow_fsm import classify_workflow_state, WorkflowState

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

### 2. CLI integration tests (in-process)

For CLI commands. Use `tmp_path` as an isolated repo root. Tests call the CLI in-process by default via `run_cli_inprocess()` from `conftest.py`:

```python
# Default: in-process call (fast, ~0.01s per invocation)
def run_cmd(tmp_path: Path, *args: str, extra_env=None) -> subprocess.CompletedProcess[str]:
    ...

# Subprocess: only for tests that need real process isolation
# (install-self, bootstrap wrapper, script shim, parallel lock)
def _run_cmd_subprocess(tmp_path: Path, *args: str, extra_env=None) -> subprocess.CompletedProcess[str]:
    ...

# Module entrypoint: tests python -m ai_agents_metrics (always subprocess)
def run_module_cmd(tmp_path: Path, *args: str, extra_env=None) -> subprocess.CompletedProcess[str]:
    ...
```

A per-test timeout of 5 seconds is enforced via `pytest-timeout` (`pyproject.toml`). Any new test exceeding this limit should use in-process execution or be investigated for unnecessary overhead.

End-to-end test pattern:

```python
from ai_agents_metrics.domain import load_metrics

def read_metrics(repo: Path) -> dict:
    return load_metrics(repo / "metrics" / "events.ndjson")

def test_start_and_finish(tmp_path: Path) -> None:
    result = run_module_cmd(tmp_path, "init")
    assert result.returncode == 0

    result = run_module_cmd(tmp_path, "start-task", "--title", "My task", "--task-type", "product")
    assert result.returncode == 0

    data = read_metrics(tmp_path)
    goals = data["goals"]
    assert len(goals) == 1
    assert goals[0]["status"] == "in_progress"
```

**Do not read `metrics/events.ndjson` with `json.loads` directly.** The file is NDJSON (one JSON object per line), not a single JSON document. Use `load_metrics()` or `replay_events()` to read it correctly.

---

## Object factories

`test_metrics_domain.py` defines factory functions with defaults and `**overrides`. They live locally in that file, not in `conftest.py`. Copy the pattern when needed:

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

> **Timestamps in dataclass factories:** `GoalRecord.started_at / finished_at` (and the equivalent fields in `AttemptEntryRecord` / `EffectiveGoalRecord`) are typed as `datetime | None`, not `str`. The dataclass factories automatically parse string values via an internal `_ts()` helper, so passing `started_at="2026-04-06T10:00:00+00:00"` to a factory is fine. However, constructing a dataclass directly (e.g. `GoalRecord(started_at="...")`) will produce a type error — use `datetime.fromisoformat(...)` or `parse_iso_datetime_flexible(...)` instead.

---

## Testing with SQLite (history pipeline)

Tests for `history_ingest` / `history_normalize` / `history_derive` require creating SQLite databases with the correct schema.

`create_codex_usage_sources(repo, ...)` in `test_metrics_cli.py` creates:
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

## Inject-corrupt-data tests

Some tests verify that `show` rejects invalid state by writing bad data directly into `events.ndjson`. These tests must write valid NDJSON events (one JSON object per line) — not raw JSON dicts or old-format payloads.

```python
def test_invalid_goal_type_fails(repo: Path) -> None:
    events_path = repo / "metrics" / "events.ndjson"
    # Write a goal_started event with an invalid field value
    invalid_goal = {"goal_id": "goal-1", "goal_type": "invalid_type", ...}
    event = {"event_type": "goal_started", "ts": "2026-01-01T00:00:00+00:00",
             "goal": invalid_goal, "entries": []}
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = run_cmd(repo, "show")
    assert result.returncode != 0
    assert "invalid_type" in result.stderr
```

**Common mistake:** writing a raw JSON dict without the expected event shape to `events.ndjson`. During replay, a line with no `event_type` field is silently skipped, so the file loads as empty state — the test passes when it should fail.

---

## Common pitfalls

**Reading the event log as JSON:**
`events.ndjson` is NDJSON, not a single JSON document. `json.loads(path.read_text())` will fail. Use `load_metrics(path)` or `replay_events(path)` instead.

**PYTHONPATH in a worktree:**
`.venv` is a symlink to the main repo. In a worktree, always use `PYTHONPATH=src` or run via `make`.

**Test mutating the real event log:**
CLI commands in end-to-end tests must be run with `cwd=tmp_path`. This makes them resolve `metrics/events.ndjson` relative to `tmp_path`, not the actual repository.
