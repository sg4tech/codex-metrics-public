
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path("scripts/update_codex_metrics.py")


def run_cmd(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)

    script_target = tmp_path / "scripts" / "update_codex_metrics.py"
    script_target.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_init_creates_files(repo: Path) -> None:
    result = run_cmd(repo, "init")
    assert result.returncode == 0, result.stderr

    metrics_path = repo / "metrics" / "codex_metrics.json"
    report_path = repo / "docs" / "codex-metrics.md"

    assert metrics_path.exists()
    assert report_path.exists()

    data = read_json(metrics_path)
    assert data["summary"]["closed_tasks"] == 0
    assert data["tasks"] == []

    report = report_path.read_text(encoding="utf-8")
    assert "Codex Metrics" in report
    assert "_No tasks recorded yet._" in report


def test_create_task_and_close_success(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    create_res = run_cmd(
        repo,
        "update",
        "--task-id",
        "task-001",
        "--title",
        "Add CSV import",
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
    assert data["summary"]["attempts_per_success"] == 1.0
    assert data["summary"]["cost_per_success_usd"] == 0.25
    assert data["summary"]["cost_per_success_tokens"] == 1000.0

    task = data["tasks"][0]
    assert task["task_id"] == "task-001"
    assert task["status"] == "success"
    assert task["attempts"] == 1
    assert task["tokens_total"] == 1000
    assert task["cost_usd"] == 0.25
    assert task["finished_at"] is not None


def test_close_fail_updates_summary(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-002",
        "--title",
        "Refactor auth flow",
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
    assert data["summary"]["attempts_per_success"] is None
    assert data["summary"]["cost_per_success_usd"] is None
    assert data["summary"]["cost_per_success_tokens"] is None

    task = data["tasks"][0]
    assert task["failure_reason"] == "validation_failed"


def test_multiple_tasks_summary(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(repo, "update", "--task-id", "t1", "--title", "Task 1").returncode == 0
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

    assert run_cmd(repo, "update", "--task-id", "t2", "--title", "Task 2").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "t2",
        "--attempts-delta",
        "4",
        "--status",
        "fail",
    ).returncode == 0

    data = read_json(repo / "metrics" / "codex_metrics.json")
    summary = data["summary"]

    assert summary["closed_tasks"] == 2
    assert summary["successes"] == 1
    assert summary["fails"] == 1
    assert summary["total_attempts"] == 6
    assert summary["success_rate"] == 0.5
    assert summary["attempts_per_success"] == 6.0
    assert summary["cost_per_success_usd"] == 0.5
    assert summary["cost_per_success_tokens"] == 500.0


def test_invalid_failure_reason_fails(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "t3", "--title", "Task 3").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "t3",
        "--failure-reason",
        "bad_reason",
    )
    assert result.returncode != 0


def test_new_task_requires_title(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "missing-title")

    assert result.returncode != 0
    assert "title is required when creating a new task" in result.stderr


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


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--attempts-delta", "-1"),
        ("--attempts", "-1"),
    ],
)
def test_negative_attempt_values_fail(repo: Path, flag: str, value: str) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(repo, "update", "--task-id", "attempt-task", "--title", "Attempt Task").returncode == 0

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
    assert run_cmd(repo, "update", "--task-id", "t4", "--title", "Task 4").returncode == 0

    result = run_cmd(repo, "update", "--task-id", "t4", flag, value)

    assert result.returncode != 0


def test_show_command(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    result = run_cmd(repo, "show")
    assert result.returncode == 0
    assert "Codex Metrics Summary" in result.stdout
    assert "Closed tasks: 0" in result.stdout


def test_report_sorts_tasks_by_started_at_descending(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "older",
        "--title",
        "Older task",
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
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--status",
        "success",
    ).returncode == 0

    report = (repo / "docs" / "codex-metrics.md").read_text(encoding="utf-8")
    newer_index = report.index("### newer")
    older_index = report.index("### older")

    assert newer_index < older_index
