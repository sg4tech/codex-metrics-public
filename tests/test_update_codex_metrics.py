
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path("scripts/update_codex_metrics.py")
PRICING = Path("pricing/model_pricing.json")


def run_cmd(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "goals" in data and "tasks" not in data:
        data["tasks"] = [
            {
                "task_id": goal["goal_id"],
                "title": goal["title"],
                "task_type": goal["goal_type"],
                "supersedes_task_id": goal.get("supersedes_goal_id"),
                "status": goal["status"],
                "attempts": goal["attempts"],
                "started_at": goal["started_at"],
                "finished_at": goal["finished_at"],
                "cost_usd": goal["cost_usd"],
                "tokens_total": goal["tokens_total"],
                "failure_reason": goal["failure_reason"],
                "notes": goal["notes"],
            }
            for goal in data["goals"]
        ]
    return data


def create_codex_usage_sources(
    repo: Path,
    thread_id: str = "thread-123",
    cwd: str | None = None,
    event_timestamp: str = "2026-03-29T09:05:00.000Z",
    model: str = "gpt-5",
    input_tokens: int = 1000,
    cached_input_tokens: int = 100,
    output_tokens: int = 500,
    reasoning_tokens: int = 0,
    tool_tokens: int = 0,
) -> tuple[Path, Path]:
    state_path = repo / "codex_state.sqlite"
    logs_path = repo / "codex_logs.sqlite"
    resolved_cwd = cwd or str(repo)

    with sqlite3.connect(state_path) as conn:
        conn.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                rollout_path TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                model_provider TEXT NOT NULL DEFAULT '',
                cwd TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                sandbox_policy TEXT NOT NULL DEFAULT '',
                approval_mode TEXT NOT NULL DEFAULT '',
                tokens_used INTEGER NOT NULL DEFAULT 0,
                has_user_event INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                archived_at INTEGER,
                git_sha TEXT,
                git_branch TEXT,
                git_origin_url TEXT,
                cli_version TEXT NOT NULL DEFAULT '',
                first_user_message TEXT NOT NULL DEFAULT '',
                agent_nickname TEXT,
                agent_role TEXT,
                memory_mode TEXT NOT NULL DEFAULT 'enabled',
                model TEXT,
                reasoning_effort TEXT,
                agent_path TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO threads (
                id, cwd, model_provider, model, created_at, updated_at, title, sandbox_policy, approval_mode, source
            ) VALUES (?, ?, 'openai', ?, 0, 0, 'Test Thread', 'workspace-write', 'default', 'desktop')
            """,
            (thread_id, resolved_cwd, model),
        )

    with sqlite3.connect(logs_path) as conn:
        conn.execute(
            """
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL DEFAULT 0,
                ts_nanos INTEGER NOT NULL DEFAULT 0,
                level TEXT NOT NULL DEFAULT 'INFO',
                target TEXT NOT NULL DEFAULT 'log',
                feedback_log_body TEXT,
                module_path TEXT,
                file TEXT,
                line INTEGER,
                thread_id TEXT,
                process_uuid TEXT,
                estimated_bytes INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO logs (feedback_log_body, thread_id)
            VALUES (?, ?)
            """,
            (
                "event.name=\"codex.sse_event\" "
                "event.kind=response.completed "
                f"input_token_count={input_tokens} "
                f"output_token_count={output_tokens} "
                f"cached_token_count={cached_input_tokens} "
                f"reasoning_token_count={reasoning_tokens} "
                f"tool_token_count={tool_tokens} "
                f"event.timestamp={event_timestamp} "
                f"conversation.id={thread_id} "
                f"model={model} "
                f"slug={model}",
                thread_id,
            ),
        )

    return state_path, logs_path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pricing").mkdir(parents=True, exist_ok=True)

    script_target = tmp_path / "scripts" / "update_codex_metrics.py"
    script_target.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    pricing_target = tmp_path / "pricing" / "model_pricing.json"
    pricing_target.write_text(PRICING.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_init_creates_files(repo: Path) -> None:
    result = run_cmd(repo, "init")
    assert result.returncode == 0, result.stderr

    metrics_path = repo / "metrics" / "codex_metrics.json"
    report_path = repo / "docs" / "codex-metrics.md"

    assert metrics_path.exists()
    assert report_path.exists()

    data = read_json(metrics_path)
    assert "goals" in data
    assert "entries" in data
    assert "tasks" in data
    assert data["summary"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["product"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["retro"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["meta"]["closed_tasks"] == 0
    assert data["tasks"] == []

    report = report_path.read_text(encoding="utf-8")
    assert "Codex Metrics" in report
    assert "_No goals recorded yet._" in report


def test_init_refuses_to_overwrite_without_force(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "init")

    assert result.returncode != 0
    assert "already exist" in result.stderr


def test_init_force_allows_overwrite(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    metrics_path = repo / "metrics" / "codex_metrics.json"
    metrics_path.write_text('{"unexpected": true}\n', encoding="utf-8")

    result = run_cmd(repo, "init", "--force")

    assert result.returncode == 0, result.stderr
    data = read_json(metrics_path)
    assert data["tasks"] == []


def test_create_task_and_close_success(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    create_res = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-001",
        "--title",
        "Add CSV import",
        "--task-type",
        "product",
    )
    assert create_res.returncode == 0, create_res.stderr

    attempt_res = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-001",
        "--attempts-delta",
        "1",
        "--tokens-add",
        "1000",
        "--cost-usd-add",
        "0.25",
    )
    assert attempt_res.returncode == 0, attempt_res.stderr

    close_res = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-001",
        "--status",
        "success",
        "--notes",
        "Completed and validated",
    )
    assert close_res.returncode == 0, close_res.stderr

    data = read_json(repo / "metrics" / "codex_metrics.json")
    assert data["summary"]["closed_tasks"] == 1
    assert data["summary"]["successes"] == 1
    assert data["summary"]["fails"] == 0
    assert data["summary"]["total_attempts"] == 1
    assert data["summary"]["success_rate"] == 1.0
    assert data["summary"]["attempts_per_closed_task"] == 1.0
    assert data["summary"]["cost_per_success_usd"] == 0.25
    assert data["summary"]["cost_per_success_tokens"] == 1000.0
    assert data["summary"]["by_task_type"]["product"]["successes"] == 1
    assert data["summary"]["by_task_type"]["retro"]["successes"] == 0

    task = data["tasks"][0]
    assert task["task_id"] == "task-001"
    assert task["task_type"] == "product"
    assert task["status"] == "success"
    assert task["attempts"] == 1
    assert task["tokens_total"] == 1000
    assert task["cost_usd"] == 0.25
    assert task["finished_at"] is not None


def test_update_can_compute_cost_from_model_pricing(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "priced-task",
        "--title",
        "Priced task",
        "--task-type",
        "product",
        "--attempts-delta",
        "1",
        "--model",
        "gpt-5",
        "--input-tokens",
        "1000",
        "--cached-input-tokens",
        "100",
        "--output-tokens",
        "500",
        "--status",
        "success",
    )
    assert result.returncode == 0, result.stderr

    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]

    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263
    assert data["summary"]["total_cost_usd"] == 0.006263
    assert data["summary"]["total_tokens"] == 1600


def test_entries_track_single_attempt_lifecycle(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-001",
        "--title",
        "Entry lifecycle task",
        "--task-type",
        "product",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-001",
        "--attempts-delta",
        "1",
        "--cost-usd-add",
        "0.10",
        "--tokens-add",
        "200",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-001",
        "--status",
        "success",
        "--notes",
        "Attempt finished cleanly",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")
    entries = [entry for entry in data["entries"] if entry["goal_id"] == "entry-task-001"]

    assert len(entries) == 1
    assert entries[0]["status"] == "success"
    assert entries[0]["failure_reason"] is None
    assert entries[0]["cost_usd"] == 0.1
    assert entries[0]["tokens_total"] == 200
    assert entries[0]["finished_at"] is not None


def test_entries_preserve_prior_attempt_when_new_attempt_starts(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-002",
        "--title",
        "Multiple attempts task",
        "--task-type",
        "product",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-002",
        "--attempts-delta",
        "1",
        "--notes",
        "First attempt started",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-002",
        "--attempts-delta",
        "1",
        "--cost-usd-add",
        "0.20",
        "--tokens-add",
        "500",
        "--notes",
        "Second attempt started",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "entry-task-002",
        "--status",
        "success",
        "--notes",
        "Second attempt succeeded",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")
    entries = sorted(
        [entry for entry in data["entries"] if entry["goal_id"] == "entry-task-002"],
        key=lambda entry: entry["entry_id"],
    )

    assert len(entries) == 2
    assert entries[0]["status"] == "fail"
    assert entries[0]["inferred"] is True
    assert entries[0]["failure_reason"] is None
    assert entries[1]["status"] == "success"
    assert entries[1]["inferred"] is False
    assert entries[1]["failure_reason"] is None
    assert entries[1]["cost_usd"] == 0.2
    assert entries[1]["tokens_total"] == 500
    assert data["summary"]["entries"]["closed_entries"] == 2
    assert data["summary"]["entries"]["successes"] == 1
    assert data["summary"]["entries"]["fails"] == 1
    assert data["summary"]["entries"]["failure_reasons"] == {}


def test_update_can_auto_sync_cost_and_tokens_from_codex_logs(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo)
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "auto-usage",
        "--title",
        "Auto usage",
        "--task-type",
        "product",
        "--status",
        "success",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:10:00+00:00",
        "--codex-state-path",
        str(state_path),
        "--codex-logs-path",
        str(logs_path),
    )
    assert result.returncode == 0, result.stderr

    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]

    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263


def test_close_fail_updates_summary(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-002",
        "--title",
        "Refactor auth flow",
        "--task-type",
        "product",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-002",
        "--attempts-delta",
        "3",
        "--status",
        "fail",
        "--failure-reason",
        "validation_failed",
        "--notes",
        "Tests failed repeatedly",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")
    assert data["summary"]["closed_tasks"] == 1
    assert data["summary"]["successes"] == 0
    assert data["summary"]["fails"] == 1
    assert data["summary"]["total_attempts"] == 3
    assert data["summary"]["success_rate"] == 0.0
    assert data["summary"]["attempts_per_closed_task"] == 3.0
    assert data["summary"]["cost_per_success_usd"] is None
    assert data["summary"]["cost_per_success_tokens"] is None
    assert data["summary"]["entries"]["failure_reasons"] == {"validation_failed": 1}

    task = data["tasks"][0]
    assert task["failure_reason"] == "validation_failed"


def test_multiple_tasks_summary(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(repo, "update", "--task-id", "t1", "--title", "Task 1", "--task-type", "product").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "t1", "--attempts-delta", "2").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "t1",
        "--status",
        "success",
        "--tokens-add",
        "500",
        "--cost-usd-add",
        "0.50",
    ).returncode == 0

    assert run_cmd(repo, "update", "--task-id", "t2", "--title", "Task 2", "--task-type", "product").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "t2",
        "--attempts-delta",
        "4",
        "--status",
        "fail",
        "--failure-reason",
        "other",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")
    summary = data["summary"]

    assert summary["closed_tasks"] == 2
    assert summary["successes"] == 1
    assert summary["fails"] == 1
    assert summary["total_attempts"] == 6
    assert summary["success_rate"] == 0.5
    assert summary["attempts_per_closed_task"] == 3.0
    assert summary["cost_per_success_usd"] == 0.5
    assert summary["cost_per_success_tokens"] == 500.0
    assert summary["by_task_type"]["product"]["closed_tasks"] == 2
    assert summary["by_task_type"]["product"]["fails"] == 1
    assert summary["entries"]["failure_reasons"] == {"other": 1}


def test_invalid_failure_reason_fails(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "t3", "--title", "Task 3", "--task-type", "product").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "t3",
        "--failure-reason",
        "bad_reason",
    )
    assert result.returncode != 0


def test_goal_type_cannot_change_after_attempt_history_exists(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "typed-goal",
        "--title",
        "Typed Goal",
        "--task-type",
        "product",
        "--attempts-delta",
        "1",
    ).returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "typed-goal",
        "--task-type",
        "meta",
    )

    assert result.returncode != 0
    assert "goal_type cannot be changed after attempt history exists" in result.stderr


def test_unknown_pricing_model_fails(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "unknown-model",
        "--title",
        "Unknown model",
        "--task-type",
        "product",
        "--model",
        "not-a-model",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
    )

    assert result.returncode != 0
    assert "Unknown pricing model" in result.stderr


def test_new_task_requires_title(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "missing-title")

    assert result.returncode != 0
    assert "title is required when creating a new task" in result.stderr


def test_new_task_requires_task_type(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "missing-task-type",
        "--title",
        "Missing task type",
    )

    assert result.returncode != 0
    assert "task_type is required when creating a new task" in result.stderr


def test_pricing_usage_cannot_mix_with_explicit_cost_or_tokens(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "mixed-pricing",
        "--title",
        "Mixed pricing",
        "--task-type",
        "product",
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
        "--cost-usd-add",
        "0.1",
    )

    assert result.returncode != 0
    assert "cannot be combined" in result.stderr


def test_cached_tokens_require_cached_rate_support(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "cached-pro",
        "--title",
        "Cached Pro",
        "--task-type",
        "product",
        "--model",
        "gpt-5-pro",
        "--cached-input-tokens",
        "100",
    )

    assert result.returncode != 0
    assert "does not support cached input pricing" in result.stderr


def test_invalid_metrics_file_format_fails(repo: Path) -> None:
    metrics_path = repo / "metrics" / "codex_metrics.json"
    metrics_path.write_text(json.dumps({"summary": {}, "tasks": [{}]}), encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode != 0
    assert "Invalid type for goal field: goal_id" in result.stderr


def test_existing_task_can_be_updated_without_title_and_keeps_started_at(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    started_at = "2026-03-29T09:00:00+00:00"
    finished_at = "2026-03-29T09:10:00+00:00"

    create_result = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-with-times",
        "--title",
        "Task with timestamps",
        "--task-type",
        "product",
        "--started-at",
        started_at,
    )
    assert create_result.returncode == 0, create_result.stderr

    close_result = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-with-times",
        "--status",
        "success",
        "--attempts-delta",
        "1",
        "--finished-at",
        finished_at,
    )
    assert close_result.returncode == 0, close_result.stderr

    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]

    assert task["title"] == "Task with timestamps"
    assert task["started_at"] == started_at
    assert task["finished_at"] == finished_at
    assert task["attempts"] == 1


def test_finished_at_cannot_be_before_started_at(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "bad-times",
        "--title",
        "Bad Times",
        "--task-type",
        "product",
        "--started-at",
        "2026-03-29T09:10:00+00:00",
        "--finished-at",
        "2026-03-29T09:00:00+00:00",
        "--status",
        "success",
    )

    assert result.returncode != 0
    assert "finished_at cannot be earlier than started_at" in result.stderr


def test_invalid_timestamp_format_fails(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "bad-timestamp",
        "--title",
        "Bad Timestamp",
        "--task-type",
        "product",
        "--started-at",
        "not-a-timestamp",
    )

    assert result.returncode != 0
    assert "Invalid started_at" in result.stderr


def test_fail_status_requires_failure_reason(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "must-fail", "--title", "Must Fail", "--task-type", "product").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "must-fail", "--status", "fail")

    assert result.returncode != 0
    assert "failure_reason is required when status is fail" in result.stderr


def test_success_status_clears_existing_failure_reason(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "recover", "--title", "Recover Task", "--task-type", "product").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "recover",
        "--status",
        "fail",
        "--failure-reason",
        "validation_failed",
    ).returncode == 0

    result = run_cmd(repo, "update", "--task-id", "recover", "--status", "success")

    assert result.returncode == 0, result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    assert data["tasks"][0]["failure_reason"] is None


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--attempts-delta", "-1"),
        ("--attempts", "-1"),
    ],
)
def test_negative_attempt_values_fail(repo: Path, flag: str, value: str) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "attempt-task", "--title", "Attempt Task", "--task-type", "product").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "attempt-task", flag, value)

    assert result.returncode != 0


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--cost-usd-add", "-0.01"),
        ("--cost-usd", "-0.01"),
        ("--tokens-add", "-1"),
        ("--tokens", "-1"),
    ],
)
def test_negative_cost_and_token_values_fail(repo: Path, flag: str, value: str) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "t4", "--title", "Task 4", "--task-type", "product").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "t4", flag, value)

    assert result.returncode != 0


def test_show_command(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    result = run_cmd(repo, "show")
    assert result.returncode == 0
    assert "Codex Metrics Summary" in result.stdout
    assert "Closed goals: 0" in result.stdout
    assert "Closed entries: 0" in result.stdout
    assert "Product goals: 0 closed, 0 successes, 0 fails" in result.stdout


def test_task_type_can_be_set_to_retro_and_is_reported_separately(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "retro-task",
        "--title",
        "Write retro",
        "--task-type",
        "retro",
        "--status",
        "success",
    )
    assert result.returncode == 0, result.stderr

    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]
    assert task["task_type"] == "retro"
    assert data["summary"]["by_task_type"]["retro"]["closed_tasks"] == 1
    assert data["summary"]["by_task_type"]["retro"]["successes"] == 1
    assert data["summary"]["by_task_type"]["product"]["closed_tasks"] == 0

    report = (repo / "docs" / "codex-metrics.md").read_text(encoding="utf-8")
    assert "### retro" in report
    assert "- Goal type: retro" in report


def test_new_task_can_link_to_closed_previous_task(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "original-task",
        "--title",
        "Original task",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--attempts",
        "1",
        "--failure-reason",
        "validation_failed",
    ).returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "followup-task",
        "--title",
        "Follow-up task",
        "--task-type",
        "product",
        "--continuation-of",
        "original-task",
        "--status",
        "success",
        "--attempts-delta",
        "1",
    )

    assert result.returncode == 0, result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    followup_task = next(task for task in data["tasks"] if task["task_id"] == "followup-task")
    assert followup_task["supersedes_task_id"] == "original-task"

    report = (repo / "docs" / "codex-metrics.md").read_text(encoding="utf-8")
    assert "- Supersedes goal: original-task" in report


def test_superseded_goal_chain_counts_as_one_effective_goal(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "goal-a",
        "--title",
        "Goal A",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--attempts",
        "1",
        "--failure-reason",
        "validation_failed",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "goal-b",
        "--title",
        "Goal B",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "goal-a",
        "--status",
        "success",
        "--attempts",
        "1",
        "--cost-usd",
        "0.25",
        "--tokens",
        "1000",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")

    assert data["summary"]["closed_tasks"] == 1
    assert data["summary"]["successes"] == 1
    assert data["summary"]["fails"] == 0
    assert data["summary"]["total_attempts"] == 2
    assert data["summary"]["attempts_per_closed_task"] == 2.0
    assert data["summary"]["cost_per_success_usd"] is None
    assert data["summary"]["by_task_type"]["product"]["closed_tasks"] == 1
    assert data["summary"]["entries"]["closed_entries"] == 2
    assert data["summary"]["entries"]["fails"] == 1
    assert data["summary"]["entries"]["successes"] == 1
    assert len(data["goals"]) == 2
    assert len(data["entries"]) == 2

    report = (repo / "docs" / "codex-metrics.md").read_text(encoding="utf-8")
    assert "## Entry summary" in report
    assert "- Closed entries: 2" in report
    assert "- Fails: 1" in report


def test_new_task_can_use_supersedes_alias(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "base-task",
        "--title",
        "Base task",
        "--task-type",
        "product",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "replacement-task",
        "--title",
        "Replacement task",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "base-task",
    )

    assert result.returncode == 0, result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    replacement_task = next(task for task in data["tasks"] if task["task_id"] == "replacement-task")
    assert replacement_task["supersedes_task_id"] == "base-task"


def test_linked_new_task_requires_existing_closed_reference(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    missing_result = run_cmd(
        repo,
        "update",
        "--task-id",
        "missing-link",
        "--title",
        "Missing link",
        "--task-type",
        "product",
        "--continuation-of",
        "no-such-task",
    )
    assert missing_result.returncode != 0
    assert "Referenced task not found" in missing_result.stderr

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "open-task",
        "--title",
        "Open task",
        "--task-type",
        "product",
    ).returncode == 0

    open_result = run_cmd(
        repo,
        "update",
        "--task-id",
        "bad-link",
        "--title",
        "Bad link",
        "--task-type",
        "product",
        "--continuation-of",
        "open-task",
    )
    assert open_result.returncode != 0
    assert "must refer to a closed task" in open_result.stderr


def test_link_flags_cannot_be_used_when_updating_existing_task(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "existing-task",
        "--title",
        "Existing task",
        "--task-type",
        "product",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "closed-task",
        "--title",
        "Closed task",
        "--task-type",
        "product",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "existing-task",
        "--continuation-of",
        "closed-task",
    )

    assert result.returncode != 0
    assert "can only be set when creating a new task" in result.stderr


def test_legacy_metrics_without_task_type_are_normalized(repo: Path) -> None:
    metrics_path = repo / "metrics" / "codex_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "summary": {
                    "closed_tasks": 1,
                    "successes": 1,
                    "fails": 0,
                    "total_attempts": 1,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "success_rate": 1.0,
                    "attempts_per_closed_task": 1.0,
                    "cost_per_success_usd": None,
                    "cost_per_success_tokens": None,
                },
                "tasks": [
                    {
                        "task_id": "legacy-task",
                        "title": "Legacy task",
                        "status": "success",
                        "attempts": 1,
                        "started_at": "2026-03-29T09:00:00+00:00",
                        "finished_at": "2026-03-29T09:01:00+00:00",
                        "cost_usd": None,
                        "tokens_total": None,
                        "failure_reason": None,
                        "notes": "Old file without task_type",
                        "supersedes_task_id": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Product goals: 1 closed, 1 successes, 0 fails" in result.stdout

    update_result = run_cmd(repo, "update", "--task-id", "legacy-task", "--notes", "Normalized")
    assert update_result.returncode == 0, update_result.stderr
    data = read_json(metrics_path)
    assert data["tasks"][0]["task_type"] == "product"
    assert data["tasks"][0]["supersedes_task_id"] is None


def test_show_preserves_small_usd_precision(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "precision-task",
        "--title",
        "Precision Task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--model",
        "gpt-5",
        "--input-tokens",
        "1000",
        "--cached-input-tokens",
        "100",
        "--output-tokens",
        "500",
    ).returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Total cost (USD): 0.006263" in result.stdout
    assert "Cost per Success (USD): 0.006263" in result.stdout


def test_sync_codex_usage_backfills_existing_tasks(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo)
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "backfill-task",
        "--title",
        "Backfill Task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:10:00+00:00",
        "--codex-state-path",
        str(repo / "missing_state.sqlite"),
        "--codex-logs-path",
        str(repo / "missing_logs.sqlite"),
    ).returncode == 0

    sync_result = run_cmd(
        repo,
        "sync-codex-usage",
        "--codex-state-path",
        str(state_path),
        "--codex-logs-path",
        str(logs_path),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]
    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263


def test_merge_tasks_combines_attempt_history_into_kept_task(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-a",
        "--title",
        "Original task",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--attempts",
        "1",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:05:00+00:00",
        "--failure-reason",
        "validation_failed",
        "--notes",
        "First attempt failed",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-b",
        "--title",
        "Replacement task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts",
        "1",
        "--started-at",
        "2026-03-29T09:06:00+00:00",
        "--finished-at",
        "2026-03-29T09:10:00+00:00",
        "--cost-usd",
        "0.25",
        "--tokens",
        "1000",
        "--notes",
        "Second attempt succeeded",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-b",
        "--drop-task-id",
        "task-a",
    )

    assert result.returncode == 0, result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    assert len(data["tasks"]) == 1
    task = data["tasks"][0]

    assert task["task_id"] == "task-b"
    assert task["status"] == "success"
    assert task["attempts"] == 2
    assert task["started_at"] == "2026-03-29T09:00:00+00:00"
    assert task["finished_at"] == "2026-03-29T09:10:00+00:00"
    assert task["failure_reason"] is None
    assert "Merged task-a into task-b" in task["notes"]
    assert data["summary"]["closed_tasks"] == 1
    assert data["summary"]["successes"] == 1
    assert data["summary"]["fails"] == 0
    assert data["summary"]["total_attempts"] == 2
    assert data["summary"]["success_rate"] == 1.0
    assert data["summary"]["attempts_per_closed_task"] == 2.0


def test_merge_tasks_keeps_cost_unknown_when_dropped_task_cost_is_missing(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-a",
        "--title",
        "Failed task",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--attempts",
        "1",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:05:00+00:00",
        "--failure-reason",
        "validation_failed",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-b",
        "--title",
        "Successful task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts",
        "1",
        "--started-at",
        "2026-03-29T09:06:00+00:00",
        "--finished-at",
        "2026-03-29T09:10:00+00:00",
        "--cost-usd",
        "0.25",
        "--tokens",
        "1000",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-b",
        "--drop-task-id",
        "task-a",
    )

    assert result.returncode == 0, result.stderr
    data = read_json(repo / "metrics" / "codex_metrics.json")
    task = data["tasks"][0]
    assert task["cost_usd"] is None
    assert task["tokens_total"] is None
    assert data["summary"]["cost_per_success_usd"] is None
    assert data["summary"]["cost_per_success_tokens"] is None


def test_merge_tasks_rejects_in_progress_tasks(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "task-a", "--title", "Open task", "--task-type", "product").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-b",
        "--title",
        "Closed task",
        "--task-type",
        "product",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-b",
        "--drop-task-id",
        "task-a",
    )

    assert result.returncode != 0
    assert "only closed goals can be merged" in result.stderr


def test_report_sorts_tasks_by_started_at_descending(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "older",
        "--title",
        "Older task",
        "--task-type",
        "product",
        "--started-at",
        "2026-03-29T08:00:00+00:00",
        "--status",
        "success",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "newer",
        "--title",
        "Newer task",
        "--task-type",
        "product",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--status",
        "success",
    ).returncode == 0

    report = (repo / "docs" / "codex-metrics.md").read_text(encoding="utf-8")
    newer_index = report.index("### newer")
    older_index = report.index("### older")

    assert newer_index < older_index
