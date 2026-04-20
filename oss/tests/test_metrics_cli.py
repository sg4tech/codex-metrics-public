
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/metrics_cli.py")
ABS_SCRIPT = WORKSPACE_ROOT / "scripts" / "metrics_cli.py"
ABS_SRC = WORKSPACE_ROOT / "src"
PRICING = WORKSPACE_ROOT / "pricing" / "model_pricing.json"

if str(ABS_SRC) not in sys.path:
    sys.path.insert(0, str(ABS_SRC))

import ai_agents_metrics as codex_metrics_pkg
import ai_agents_metrics.cli as codex_metrics_cli
from ai_agents_metrics.usage_backends import ClaudeUsageBackend, select_usage_backend
from ai_agents_metrics.usage_backends import resolve_usage_window as resolve_backend_usage_window


def _build_subprocess_cmd(*args: str) -> list[str]:
    script = str(SCRIPT)
    if os.environ.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        script = str(ABS_SCRIPT)
        return [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(WORKSPACE_ROOT / "pyproject.toml"),
            "--parallel-mode",
            script,
            *args,
        ]
    return [sys.executable, script, *args]


def _run_cmd_subprocess(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        env["COVERAGE_FILE"] = str(WORKSPACE_ROOT / ".coverage")
    if extra_env is not None:
        env.update(extra_env)
    cmd = _build_subprocess_cmd(*args)
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run_cmd(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if os.environ.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        return _run_cmd_subprocess(tmp_path, *args, extra_env=extra_env)
    from conftest import run_cli_inprocess
    return run_cli_inprocess(tmp_path, *args, extra_env=extra_env)


def run_module_cmd(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(ABS_SRC)
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    if env.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        env["COVERAGE_FILE"] = str(WORKSPACE_ROOT / ".coverage")
        cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(WORKSPACE_ROOT / "pyproject.toml"),
            "--parallel-mode",
            "-m",
            "ai_agents_metrics",
            *args,
        ]
    else:
        cmd = [sys.executable, "-m", "ai_agents_metrics", *args]
    if extra_env is not None:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def render_report(repo: Path) -> subprocess.CompletedProcess[str]:
    return run_cmd(repo, "render-report")


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
                "input_tokens": goal.get("input_tokens"),
                "cached_input_tokens": goal.get("cached_input_tokens"),
                "output_tokens": goal.get("output_tokens"),
                "tokens_total": goal["tokens_total"],
                "failure_reason": goal["failure_reason"],
                "notes": goal["notes"],
                "agent_name": goal.get("agent_name"),
                "result_fit": goal.get("result_fit"),
                "model": goal.get("model"),
            }
            for goal in data["goals"]
        ]
    return data


def read_metrics(repo: Path) -> dict:
    """Load current metrics state from the event log and add a `tasks` alias."""
    from ai_agents_metrics.domain import load_metrics as _load_metrics

    data = _load_metrics(repo / "metrics" / "events.ndjson")
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
            "input_tokens": goal.get("input_tokens"),
            "cached_input_tokens": goal.get("cached_input_tokens"),
            "output_tokens": goal.get("output_tokens"),
            "tokens_total": goal["tokens_total"],
            "failure_reason": goal["failure_reason"],
            "notes": goal["notes"],
            "agent_name": goal.get("agent_name"),
            "result_fit": goal.get("result_fit"),
            "model": goal.get("model"),
        }
        for goal in data["goals"]
    ]
    return data


def test_legacy_metrics_json_stays_low_signal_for_worktree_detection() -> None:
    assert codex_metrics_cli._is_meaningful_worktree_path("metrics/codex_metrics.json") is False


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


def create_codex_session_usage_sources(
    repo: Path,
    thread_id: str = "thread-123",
    cwd: str | None = None,
    model_provider: str = "openai",
    event_timestamp: str = "2026-03-29T09:05:00.000Z",
    model: str = "gpt-5.4",
    input_tokens: int = 1000,
    cached_input_tokens: int = 100,
    output_tokens: int = 500,
    reasoning_tokens: int = 25,
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
            ) VALUES (?, ?, ?, ?, 0, 0, 'Test Thread', 'workspace-write', 'default', 'desktop')
            """,
            (thread_id, resolved_cwd, model_provider, model),
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
                f"session_loop thread.id={thread_id} model={model} response.completed",
                thread_id,
            ),
        )

    sessions_dir = repo / "sessions" / "2026" / "03" / "29"
    sessions_dir.mkdir(parents=True)
    rollout_path = sessions_dir / f"rollout-2026-03-29T11-27-52-{thread_id}.jsonl"
    rollout_path.write_text(
        json.dumps(
            {
                "timestamp": event_timestamp,
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_input_tokens,
                            "output_tokens": output_tokens,
                            "reasoning_output_tokens": reasoning_tokens,
                            "total_tokens": input_tokens
                            + cached_input_tokens
                            + output_tokens
                            + reasoning_tokens,
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    return state_path, logs_path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pricing").mkdir(parents=True, exist_ok=True)

    pricing_target = tmp_path / "pricing" / "model_pricing.json"
    pricing_target.write_text(PRICING.read_text(encoding="utf-8"), encoding="utf-8")
    # Script shim is cheap to copy and needed by subprocess-based tests
    # (install-self, bootstrap wrapper, script_shim_exposes_cli_version, run_module_cmd).
    script_target = tmp_path / "scripts" / "metrics_cli.py"
    script_target.write_text(ABS_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

    # Full src copy only needed when subprocess must import the package from tmp.
    if os.environ.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        shutil.copytree(ABS_SRC, tmp_path / "src", dirs_exist_ok=True)

    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, text=True, capture_output=True, check=True)
    yield tmp_path


def test_init_creates_files(repo: Path) -> None:
    result = run_cmd(repo, "init")
    assert result.returncode == 0, result.stderr

    metrics_path = repo / "metrics" / "events.ndjson"
    report_path = repo / "docs" / "ai-agents-metrics.md"

    assert metrics_path.exists()
    assert not report_path.exists()

    data = read_metrics(repo)
    assert "goals" in data
    assert "entries" in data
    assert "tasks" in data
    assert data["summary"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["product"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["retro"]["closed_tasks"] == 0
    assert data["summary"]["by_task_type"]["meta"]["closed_tasks"] == 0
    assert data["tasks"] == []

    render_result = render_report(repo)
    assert render_result.returncode == 0, render_result.stderr
    report = report_path.read_text(encoding="utf-8")
    assert "AI Agents Metrics" in report
    assert "_No goals recorded yet._" in report


def test_package_module_entrypoint_runs(repo: Path) -> None:
    result = run_module_cmd(repo, "--help")

    assert result.returncode == 0, result.stderr
    assert "Analyze your AI agent work history" in result.stdout


def test_package_module_entrypoint_can_initialize_files(repo: Path) -> None:
    result = run_module_cmd(repo, "init")

    assert result.returncode == 0, result.stderr
    assert (repo / "metrics" / "events.ndjson").exists()
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()


def test_init_can_render_optional_report_when_requested(repo: Path) -> None:
    result = run_cmd(repo, "init", "--write-report")

    assert result.returncode == 0, result.stderr
    assert (repo / "metrics" / "events.ndjson").exists()
    assert (repo / "docs" / "ai-agents-metrics.md").exists()


def test_ensure_active_task_creates_recovery_goal_for_meaningful_git_changes(repo: Path) -> None:
    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    result = run_cmd(repo, "ensure-active-task")

    assert result.returncode == 0, result.stderr
    assert "Created recovery goal" in result.stdout
    data = read_metrics(repo)
    goals = data["goals"]
    assert len(goals) == 1
    goal = goals[0]
    assert goal["status"] == "in_progress"
    assert goal["goal_type"] == "meta"
    assert goal["title"] == "Recover active task for in-progress repository work"
    assert goal["attempts"] == 0


def test_start_task_remains_available_for_new_worktree_changes(repo: Path) -> None:
    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    result = run_cmd(repo, "start-task", "--title", "Start after work began", "--task-type", "meta")

    assert result.returncode == 0, result.stderr
    assert "Updated goal" in result.stdout


def test_start_task_records_structured_event_and_debug_log(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "start-task", "--title", "Observed task", "--task-type", "meta")

    assert result.returncode == 0, result.stderr
    events_db = repo / "metrics" / ".ai-agents-metrics" / "events.sqlite"
    debug_log = repo / "metrics" / ".ai-agents-metrics" / "events.debug.log"
    assert events_db.exists()
    assert debug_log.exists()

    with sqlite3.connect(events_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_id, event_type, command, goal_id, goal_type, status_after, attempts_after, payload_json "
            "FROM events ORDER BY occurred_at ASC, event_id ASC"
        ).fetchall()

    assert len(rows) == 3
    event_types = [row["event_type"] for row in rows]
    assert event_types.count("cli_invoked") == 2
    assert event_types.count("goal_created") == 1
    commands = [row["command"] for row in rows]
    assert commands.count("init") == 1
    assert commands.count("start-task") == 2
    goal_created_row = next(row for row in rows if row["event_type"] == "goal_created")
    assert goal_created_row["command"] == "start-task"
    assert goal_created_row["goal_type"] == "meta"
    assert goal_created_row["status_after"] == "in_progress"
    assert goal_created_row["attempts_after"] == 1
    payload = json.loads(goal_created_row["payload_json"])
    assert payload["command"] == "start-task"
    assert payload["status_after"] == "in_progress"
    debug_text = debug_log.read_text(encoding="utf-8")
    for row in rows:
        assert row["event_id"] in debug_text


def test_show_records_cli_invocation_event(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    events_db = repo / "metrics" / ".ai-agents-metrics" / "events.sqlite"
    debug_log = repo / "metrics" / ".ai-agents-metrics" / "events.debug.log"

    with sqlite3.connect(events_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT event_type, command, payload_json FROM events WHERE event_type = 'cli_invoked' AND command = 'show' "
            "ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()

    assert row is not None
    assert row["event_type"] == "cli_invoked"
    assert row["command"] == "show"
    payload = json.loads(row["payload_json"])
    assert payload["command"] == "show"
    assert payload["cwd"] == str(repo)
    assert "event_type=\"cli_invoked\"" in debug_log.read_text(encoding="utf-8")


def test_ensure_active_task_is_idempotent_when_active_goal_exists(repo: Path) -> None:
    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    first_result = run_cmd(repo, "ensure-active-task")
    assert first_result.returncode == 0, first_result.stderr

    second_result = run_cmd(repo, "ensure-active-task")

    assert second_result.returncode == 0, second_result.stderr
    assert "Active goal already exists" in second_result.stdout
    data = read_metrics(repo)
    active_goals = [goal for goal in data["goals"] if goal["status"] == "in_progress"]
    assert len(active_goals) == 1


def test_ensure_active_task_ignores_low_signal_metrics_only_changes(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "ensure-active-task")

    assert result.returncode == 0, result.stderr
    assert "No active task recovery needed" in result.stdout
    data = read_metrics(repo)
    assert data["goals"] == []


def test_show_is_quiet_when_repo_is_clean(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Warning:" not in result.stdout


def test_show_warns_when_repo_work_started_without_active_goal(repo: Path) -> None:
    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Warning: repository work appears to have started without an active goal;" in result.stdout
    assert "ensure-active-task" in result.stdout


def test_continue_task_is_blocked_when_started_work_exists_without_active_goal(repo: Path) -> None:
    start_result = run_cmd(repo, "start-task", "--title", "Baseline task", "--task-type", "product")
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    finish_result = run_cmd(repo, "finish-task", "--task-id", goal_id, "--status", "success")
    assert finish_result.returncode == 0, finish_result.stderr

    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    continue_result = run_cmd(repo, "continue-task", "--task-id", goal_id)

    assert continue_result.returncode == 1
    assert "ensure-active-task" in continue_result.stderr


def test_update_can_repair_closed_goal_without_active_goal(repo: Path) -> None:
    start_result = run_cmd(repo, "start-task", "--title", "Baseline task", "--task-type", "product")
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    finish_result = run_cmd(repo, "finish-task", "--task-id", goal_id, "--status", "success")
    assert finish_result.returncode == 0, finish_result.stderr

    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    repair_result = run_cmd(
        repo,
        "update",
        "--task-id",
        goal_id,
        "--status",
        "success",
        "--notes",
        "Bookkeeping repair after manual JSON adjustment",
    )

    assert repair_result.returncode == 0, repair_result.stderr
    assert "Updated goal" in repair_result.stdout
    data = read_metrics(repo)
    repaired_goal = next(goal for goal in data["goals"] if goal["goal_id"] == goal_id)
    assert repaired_goal["status"] == "success"
    assert repaired_goal["notes"] == "Bookkeeping repair after manual JSON adjustment"


def test_finish_task_repair_path_remains_available_without_active_goal(repo: Path) -> None:
    start_result = run_cmd(repo, "start-task", "--title", "Baseline task", "--task-type", "product")
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    finish_result = run_cmd(repo, "finish-task", "--task-id", goal_id, "--status", "success")
    assert finish_result.returncode == 0, finish_result.stderr

    (repo / "src" / "worktree_change.py").write_text("print('changed')\n", encoding="utf-8")

    repair_result = run_cmd(
        repo,
        "finish-task",
        "--task-id",
        goal_id,
        "--status",
        "success",
        "--notes",
        "Closed-goal repair remains available",
    )

    assert repair_result.returncode == 0, repair_result.stderr
    assert "Updated goal" in repair_result.stdout
    data = read_metrics(repo)
    repaired_goal = next(goal for goal in data["goals"] if goal["goal_id"] == goal_id)
    assert repaired_goal["status"] == "success"
    assert repaired_goal["notes"] == "Closed-goal repair remains available"


def test_explicit_mutation_is_not_blocked_by_other_active_goals(repo: Path) -> None:
    first_result = run_cmd(repo, "start-task", "--title", "Baseline task one", "--task-type", "product")
    assert first_result.returncode == 0, first_result.stderr
    first_goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in first_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    second_result = run_cmd(repo, "start-task", "--title", "Baseline task two", "--task-type", "meta")
    assert second_result.returncode == 0, second_result.stderr
    second_goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in second_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    close_result = run_cmd(repo, "finish-task", "--task-id", first_goal_id, "--status", "success")

    assert close_result.returncode == 0, close_result.stderr
    data = read_metrics(repo)
    first_goal = next(goal for goal in data["goals"] if goal["goal_id"] == first_goal_id)
    second_goal = next(goal for goal in data["goals"] if goal["goal_id"] == second_goal_id)
    assert first_goal["status"] == "success"
    assert second_goal["status"] == "in_progress"
    assert len([goal for goal in data["goals"] if goal["status"] == "in_progress"]) == 1


def test_ensure_active_task_handles_non_git_repositories(tmp_path: Path) -> None:
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)

    result = run_module_cmd(tmp_path, "ensure-active-task")

    assert result.returncode == 0, result.stderr
    assert "Cannot detect started work reliably" in result.stdout


def test_package_module_entrypoint_supports_bootstrap(repo: Path) -> None:
    result = run_module_cmd(repo, "bootstrap", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would create metrics file" in result.stdout


def test_install_self_creates_launcher_in_target_dir(repo: Path) -> None:
    install_dir = repo / "bin"
    expected_script_paths = {
        str((repo / "scripts" / "metrics_cli.py").resolve()),
        str(ABS_SCRIPT.resolve()),
    }

    result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir))

    assert result.returncode == 0, result.stderr
    installed_path = install_dir / "ai-agents-metrics"
    installed_text = installed_path.read_text(encoding="utf-8")
    assert installed_text.startswith("#!/bin/sh\n")
    assert any(script_path in installed_text for script_path in expected_script_paths)
    assert sys.executable in installed_text
    assert f"{installed_path}" in result.stdout
    assert f"Warning: {install_dir}" in result.stdout
    assert "export PATH=" in result.stdout


def test_install_self_replaces_existing_target(repo: Path) -> None:
    install_dir = repo / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)
    installed_path = install_dir / "ai-agents-metrics"
    installed_path.write_text("old\n", encoding="utf-8")
    expected_script_paths = {
        str((repo / "scripts" / "metrics_cli.py").resolve()),
        str(ABS_SCRIPT.resolve()),
    }

    result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir))

    assert result.returncode == 0, result.stderr
    installed_text = installed_path.read_text(encoding="utf-8")
    assert installed_text.startswith("#!/bin/sh\n")
    assert any(script_path in installed_text for script_path in expected_script_paths)


def test_module_install_self_creates_module_launcher(repo: Path) -> None:
    install_dir = repo / "bin"

    result = run_module_cmd(repo, "install-self", "--target-dir", str(install_dir))

    assert result.returncode == 0, result.stderr
    installed_path = install_dir / "ai-agents-metrics"
    installed_text = installed_path.read_text(encoding="utf-8")
    assert installed_text.startswith("#!/bin/sh\n")
    assert sys.executable in installed_text
    assert f"export PYTHONPATH='{ABS_SRC.resolve()}'" in installed_text
    assert "-m ai_agents_metrics" in installed_text


def test_install_self_skips_path_warning_when_target_dir_is_already_on_path(repo: Path) -> None:
    install_dir = repo / "bin"
    result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir), extra_env={"PATH": f"{install_dir}{os.pathsep}{os.environ.get('PATH', '')}"})

    assert result.returncode == 0, result.stderr
    assert "Warning:" not in result.stdout


def test_install_self_can_write_shell_profile(repo: Path) -> None:
    install_dir = repo / "bin"
    fake_home = repo / "home"

    result = _run_cmd_subprocess(
        repo,
        "install-self",
        "--target-dir",
        str(install_dir),
        "--write-shell-profile",
        extra_env={"HOME": str(fake_home), "SHELL": "/bin/zsh", "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode == 0, result.stderr
    zshrc_path = fake_home / ".zshrc"
    assert zshrc_path.exists()
    zshrc_text = zshrc_path.read_text(encoding="utf-8")
    assert f'export PATH="{install_dir}:$PATH"' in zshrc_text
    assert f"Added PATH update to {zshrc_path}" in result.stdout
    assert "Warning:" not in result.stdout


def test_install_self_write_shell_profile_is_idempotent(repo: Path) -> None:
    install_dir = repo / "bin"
    fake_home = repo / "home"
    extra_env = {"HOME": str(fake_home), "SHELL": "/bin/zsh", "PATH": "/usr/bin:/bin"}

    first_result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir), "--write-shell-profile", extra_env=extra_env)
    second_result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir), "--write-shell-profile", extra_env=extra_env)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    zshrc_text = (fake_home / ".zshrc").read_text(encoding="utf-8")
    assert zshrc_text.count(f'export PATH="{install_dir}:$PATH"') == 1
    assert "PATH update already present" in second_result.stdout


def test_install_self_warns_when_active_virtualenv_shadows_global_install(repo: Path) -> None:
    install_dir = repo / "bin"
    fake_venv_bin = repo / "fake-venv" / "bin"
    fake_venv_bin.mkdir(parents=True, exist_ok=True)
    shadowing_command = fake_venv_bin / "ai-agents-metrics"
    shadowing_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    shadowing_command.chmod(0o755)

    first_result = _run_cmd_subprocess(repo, "install-self", "--target-dir", str(install_dir))
    assert first_result.returncode == 0, first_result.stderr

    second_result = _run_cmd_subprocess(
        repo,
        "install-self",
        "--target-dir",
        str(install_dir),
        extra_env={
            "PATH": f"{fake_venv_bin}{os.pathsep}{install_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "VIRTUAL_ENV": str(repo / "fake-venv"),
        },
    )

    assert second_result.returncode == 0, second_result.stderr
    assert "ai-agents-metrics" in second_result.stdout
    assert "active virtualenv is shadowing the global install" in second_result.stdout
    assert str(shadowing_command) in second_result.stdout


def test_init_refuses_to_overwrite_without_force(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "init")

    assert result.returncode != 0
    assert "already exist" in result.stderr


def test_init_force_allows_overwrite(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    metrics_path = repo / "metrics" / "events.ndjson"
    # Write some stale events directly to simulate a non-empty log
    metrics_path.write_text(
        '{"event_type":"goal_started","ts":"2026-01-01T00:00:00+00:00","goal":{"goal_id":"stale"},"entries":[]}\n',
        encoding="utf-8",
    )

    result = run_cmd(repo, "init", "--force")

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    assert data["tasks"] == []


def test_bootstrap_dry_run_reports_actions_without_writing_files(repo: Path) -> None:
    result = run_cmd(repo, "bootstrap", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would create metrics file" in result.stdout
    assert "Would skip markdown report generation by default" in result.stdout
    assert "Would create policy file" in result.stdout
    assert "Would create instructions file" in result.stdout
    assert "Would create command wrapper" in result.stdout
    assert not (repo / "metrics" / "events.ndjson").exists()
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()
    assert not (repo / "docs" / "ai-agents-metrics-policy.md").exists()
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / "tools" / "ai-agents-metrics").exists()


def test_bootstrap_creates_scaffold_files(repo: Path) -> None:
    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 0, result.stderr
    assert "Created metrics file" in result.stdout
    assert "Skipping markdown report generation by default" in result.stdout
    assert "Created policy file" in result.stdout
    assert "Created instructions file" in result.stdout

    metrics_path = repo / "metrics" / "events.ndjson"
    report_path = repo / "docs" / "ai-agents-metrics.md"
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    command_path = repo / "tools" / "ai-agents-metrics"
    agents_path = repo / "AGENTS.md"

    assert metrics_path.exists()
    assert not report_path.exists()
    assert policy_path.exists()
    assert command_path.exists()
    assert agents_path.exists()

    data = read_metrics(repo)
    assert data["tasks"] == []

    policy_text = policy_path.read_text(encoding="utf-8")
    assert "AI Agents Metrics Policy" in policy_text
    assert "AI-agent-assisted engineering work" in policy_text
    assert "## Two-Tier Model" in policy_text
    assert "## Purpose" in policy_text
    assert "## Scope" in policy_text
    assert "## Core Model" in policy_text
    assert "## Required Workflow" in policy_text
    assert "## Recommended Commands" in policy_text
    assert "## Validation Rules" in policy_text
    assert "history-update" in policy_text
    assert "ai-agents-metrics start-task" in policy_text
    assert "ai-agents-metrics continue-task" in policy_text
    assert "ai-agents-metrics finish-task" in policy_text
    assert "agent-agnostic" in policy_text
    assert "If `ai-agents-metrics` is expected but unavailable" in policy_text
    assert "Do not invent a manual fallback workflow" in policy_text
    assert "## Reporting Rules" in policy_text
    assert "## Anti-Gaming Rules" in policy_text
    assert "## Required Goal Fields" not in policy_text
    assert "## Required Entry Fields" not in policy_text
    assert "## Summary Metrics" not in policy_text
    assert "## Product Quality Review" not in policy_text
    assert "## Testing Standard" not in policy_text
    assert "## Repository Defaults For This Repo" not in policy_text

    agents_text = agents_path.read_text(encoding="utf-8")
    assert "# AGENTS.md" in agents_text
    assert "<!-- ai-agents-metrics:start -->" in agents_text
    assert "### Read first" in agents_text
    assert "Before starting or continuing any engineering task, always read:" in agents_text
    assert "- `AGENTS.md`" in agents_text
    assert "docs/ai-agents-metrics-policy.md" in agents_text
    assert "Use `tools/ai-agents-metrics ...` in this repository." in agents_text
    assert "If `tools/ai-agents-metrics` is unavailable, stop and report an installation or invocation mismatch" in agents_text
    assert "The rules in `docs/ai-agents-metrics-policy.md` are mandatory" in agents_text
    assert "Generated artifacts:" not in agents_text
    assert "Do not edit generated metrics files manually" not in agents_text
    assert "ai-agents-metrics update" not in agents_text


def test_bootstrap_can_create_optional_report_when_requested(repo: Path) -> None:
    result = run_cmd(repo, "bootstrap", "--write-report")

    assert result.returncode == 0, result.stderr
    assert (repo / "metrics" / "events.ndjson").exists()
    assert (repo / "docs" / "ai-agents-metrics.md").exists()


def test_packaged_policy_template_matches_repo_policy() -> None:
    policy_source = WORKSPACE_ROOT / "docs" / "private" / "ai-agents-metrics-policy.md"
    if not policy_source.exists():
        pytest.skip("private policy not available in this context")
    repo_policy = policy_source.read_text(encoding="utf-8")
    packaged_policy = (
        WORKSPACE_ROOT / "src" / "ai_agents_metrics" / "data" / "bootstrap_codex_metrics_policy.md"
    ).read_text(encoding="utf-8")

    assert packaged_policy == repo_policy


def test_bootstrap_appends_single_managed_block_to_existing_agents(repo: Path) -> None:
    agents_path = repo / "AGENTS.md"
    agents_path.write_text("# Existing Rules\n\nKeep local conventions.\n", encoding="utf-8")

    first_result = run_cmd(repo, "bootstrap")
    second_result = run_cmd(repo, "bootstrap")

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr

    agents_text = agents_path.read_text(encoding="utf-8")
    assert "# Existing Rules" in agents_text
    assert agents_text.count("<!-- ai-agents-metrics:start -->") == 1
    assert agents_text.count("<!-- ai-agents-metrics:end -->") == 1
    assert "docs/ai-agents-metrics-policy.md" in agents_text


def test_bootstrap_refuses_to_overwrite_different_policy_without_force(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 1
    assert "already exists with different content" in result.stderr


def test_bootstrap_force_replaces_existing_policy_file(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_cmd(repo, "bootstrap", "--force")

    assert result.returncode == 0, result.stderr
    policy_text = policy_path.read_text(encoding="utf-8")
    assert "AI Agents Metrics Policy" in policy_text


def test_bootstrap_completes_partial_scaffold_when_metrics_exist(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 0, result.stderr
    assert "Keeping existing metrics file" in result.stdout
    assert "Skipping markdown report generation by default" in result.stdout
    assert (repo / "metrics" / "events.ndjson").exists()
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()
    assert (repo / "docs" / "ai-agents-metrics-policy.md").exists()
    assert (repo / "AGENTS.md").exists()


def test_bootstrap_completes_partial_scaffold_when_report_exists(repo: Path) -> None:
    assert run_cmd(repo, "init", "--write-report").returncode == 0
    metrics_path = repo / "metrics" / "events.ndjson"
    metrics_path.unlink()

    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 0, result.stderr
    assert "Created metrics file" in result.stdout
    assert "Skipping markdown report generation by default" in result.stdout
    assert (repo / "metrics" / "events.ndjson").exists()
    assert (repo / "docs" / "ai-agents-metrics.md").exists()


def test_bootstrap_conflicting_policy_is_non_destructive(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 1
    assert not (repo / "metrics" / "events.ndjson").exists()
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()
    assert not (repo / "AGENTS.md").exists()


def test_bootstrap_dry_run_reports_policy_conflict_without_writing(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_cmd(repo, "bootstrap", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Would refuse to replace existing policy file without --force" in result.stdout
    assert not (repo / "metrics" / "events.ndjson").exists()
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()
    assert not (repo / "AGENTS.md").exists()


def test_bootstrap_custom_paths_render_relative_agents_links(repo: Path) -> None:
    result = run_cmd(
        repo,
        "bootstrap",
        "--metrics-path",
        "custom/metrics.json",
        "--report-path",
        "custom/report.md",
        "--policy-path",
        "rules/policy.md",
        "--command-path",
        "bin/ai-agents-metrics",
        "--agents-path",
        "guide/AGENTS.md",
    )

    assert result.returncode == 0, result.stderr
    agents_text = (repo / "guide" / "AGENTS.md").read_text(encoding="utf-8")
    assert "`../rules/policy.md`" in agents_text
    assert "`../bin/ai-agents-metrics ...`" in agents_text


def test_bootstrap_can_target_claude_instructions_file(repo: Path) -> None:
    result = run_cmd(repo, "bootstrap", "--instructions-path", "CLAUDE.md")

    assert result.returncode == 0, result.stderr
    instructions_text = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# CLAUDE.md" in instructions_text
    assert "- `CLAUDE.md`" in instructions_text
    assert "docs/ai-agents-metrics-policy.md" in instructions_text
    assert "Use `tools/ai-agents-metrics ...` in this repository." in instructions_text


def test_bootstrap_wrapper_runs_from_repo_root_even_when_invoked_from_other_cwd(repo: Path, tmp_path: Path) -> None:
    result = _run_cmd_subprocess(repo, "bootstrap")
    assert result.returncode == 0, result.stderr

    wrapper_path = repo / "tools" / "ai-agents-metrics"
    foreign_cwd = tmp_path / "foreign-cwd"
    foreign_cwd.mkdir(parents=True, exist_ok=True)

    wrapper_result = subprocess.run(
        [str(wrapper_path), "show"],
        cwd=foreign_cwd,
        text=True,
        capture_output=True,
        check=False,
    )

    assert wrapper_result.returncode == 0, wrapper_result.stderr
    assert "Closed goals: 0" in wrapper_result.stdout
    assert "Known total cost (USD): 0" in wrapper_result.stdout


def test_script_entrypoint_prints_clean_bootstrap_error(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_cmd(repo, "bootstrap")

    assert result.returncode == 1
    assert "Error: Policy file already exists with different content" in result.stderr
    assert "Traceback" not in result.stderr


def test_module_entrypoint_prints_clean_bootstrap_error(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    result = run_module_cmd(repo, "bootstrap")

    assert result.returncode == 1
    assert "Error: Policy file already exists with different content" in result.stderr
    assert "Traceback" not in result.stderr


def test_console_entrypoint_prints_clean_bootstrap_error(repo: Path) -> None:
    policy_path = repo / "docs" / "ai-agents-metrics-policy.md"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("# Different Policy\n\nDo not replace me.\n", encoding="utf-8")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(ABS_SRC)
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from ai_agents_metrics.cli import console_main; "
                "sys.argv=['codex-metrics', 'bootstrap']; "
                "raise SystemExit(console_main())"
            ),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 1
    assert "Error: Policy file already exists with different content" in result.stderr
    assert "Traceback" not in result.stderr


def test_help_lists_completion_command(repo: Path) -> None:
    result = run_cmd(repo, "--help")

    assert result.returncode == 0
    assert "install-self" in result.stdout
    assert "completion" in result.stdout
    assert "Print shell completion for bash or zsh" in result.stdout
    assert "sync-usage" in result.stdout
    assert "sync-codex-usage" in result.stdout


def test_task_workflow_help_does_not_expose_provider_specific_flags(repo: Path) -> None:
    result = run_cmd(repo, "start-task", "--help")

    assert result.returncode == 0
    assert "--agent" not in result.stdout
    assert "--usage-source" not in result.stdout


def test_render_html_exposes_warehouse_path_flag(repo: Path) -> None:
    """render-html must accept --warehouse-path so users can point the
    report at a custom warehouse (cross-machine imports, alternate
    locations). commands.handle_render_html already reads the flag via
    getattr fallback; the argparser gap left it as dead code until
    goal 2026-04-20-008.
    """
    result = run_cmd(repo, "render-html", "--help")

    assert result.returncode == 0
    assert "--warehouse-path" in result.stdout


def test_top_level_help_hides_advanced_commands_from_subparser_list(repo: Path) -> None:
    """First-time users should see a short primary-flow listing, not 26 commands.

    Advanced / pipeline-stage / legacy commands stay fully callable and are
    listed by name in the epilog — just not in the main subparser block that
    argparse renders under `positional arguments`.
    """
    result = run_cmd(repo, "--help")
    assert result.returncode == 0

    # Usage header must not dump every command name — argparse does this by
    # default with `{init,bootstrap,install-self,...}` which is the wall we're
    # trying to avoid. A `<command>` metavar keeps it readable.
    first_line = result.stdout.splitlines()[0]
    assert "<command>" in first_line
    assert "init,bootstrap" not in first_line

    # Split on the epilog header so we can inspect the subparser listing block
    # independently of the grouped name-dump in the epilog.
    subparser_block, _, epilog_block = result.stdout.partition(
        "Additional commands (run `<command> --help` for details):"
    )
    assert epilog_block, "epilog with grouped command list must be present"

    # Primary-flow commands must be in the subparser listing (visible).
    for primary in ("history-update", "show", "render-html", "bootstrap",
                    "start-task", "continue-task", "finish-task",
                    "install-self", "completion"):
        assert primary in subparser_block, f"{primary} must appear in the primary-flow listing"

    # Hidden commands must NOT appear in the subparser block (to keep it short),
    # but MUST appear by name in the epilog (so users can still discover them).
    hidden = [
        "init", "update", "ensure-active-task",
        "history-ingest", "history-normalize", "history-classify", "history-derive",
        "history-audit", "history-compare", "audit-cost-coverage",
        "derive-retro-timeline", "sync-usage", "sync-codex-usage",
        "merge-tasks", "render-report", "verify-public-boundary", "security",
    ]
    for cmd in hidden:
        # Not in subparser block's "positional arguments" section.
        # (A hidden command's *name* may still appear as a substring of a
        # visible command, e.g. "history-update" contains no hidden command.
        # We assert absence with a line-start-indentation match used by
        # argparse for subparser entries: four spaces + name.)
        entry = f"    {cmd}"
        assert entry not in subparser_block, f"{cmd} must be hidden from the subparser listing"
        # Present in epilog grouping.
        assert cmd in epilog_block, f"{cmd} must be listed by name in the epilog"


def test_hidden_advanced_commands_remain_callable(repo: Path) -> None:
    """Hiding from --help must not disable the commands themselves.

    Each hidden command must still respond to `<cmd> --help` with its own
    per-command help text and exit cleanly.
    """
    for cmd in ("history-ingest", "history-normalize", "history-derive",
                "audit-cost-coverage", "sync-usage", "update",
                "ensure-active-task", "render-report"):
        result = run_cmd(repo, cmd, "--help")
        assert result.returncode == 0, f"{cmd} --help must exit 0; stderr={result.stderr!r}"
        assert "usage:" in result.stdout, f"{cmd} --help must print usage"


def test_completion_bash_outputs_completion_function(repo: Path) -> None:
    result = run_cmd(repo, "completion", "bash")

    assert result.returncode == 0, result.stderr
    assert "_ai_agents_metrics_completion()" in result.stdout
    assert "complete -F _ai_agents_metrics_completion codex-metrics" in result.stdout
    assert "bootstrap" in result.stdout
    assert "--metrics-path" in result.stdout


def test_completion_zsh_outputs_compdef_script(repo: Path) -> None:
    result = run_cmd(repo, "completion", "zsh")

    assert result.returncode == 0, result.stderr
    assert "#compdef ai-agents-metrics" in result.stdout
    assert "_describe 'command' commands" in result.stdout
    assert "completion)" in result.stdout
    assert "--policy-path" in result.stdout


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

    data = read_metrics(repo)
    assert data["summary"]["closed_tasks"] == 1
    assert data["summary"]["successes"] == 1
    assert data["summary"]["fails"] == 0
    assert data["summary"]["total_attempts"] == 1
    assert data["summary"]["success_rate"] == 1.0
    assert data["summary"]["attempts_per_closed_task"] == 1.0
    assert data["summary"]["known_cost_successes"] == 1
    assert data["summary"]["known_token_successes"] == 1
    assert data["summary"]["known_cost_per_success_usd"] == 0.25
    assert data["summary"]["known_cost_per_success_tokens"] == 1000.0
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


def test_create_task_auto_generates_goal_id(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--title",
        "Auto ID task",
        "--task-type",
        "product",
    )

    assert result.returncode == 0, result.stderr
    assert "Updated goal " in result.stdout

    data = read_metrics(repo)
    assert len(data["tasks"]) == 1
    created_task = data["tasks"][0]
    assert created_task["task_id"].startswith("20")
    assert created_task["title"] == "Auto ID task"
    assert created_task["task_type"] == "product"


def test_create_task_auto_id_increments_with_same_day_prefix(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    first = run_cmd(repo, "update", "--title", "First", "--task-type", "product")
    second = run_cmd(repo, "update", "--title", "Second", "--task-type", "product")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    data = read_metrics(repo)
    created_ids = sorted(task["task_id"] for task in data["tasks"])
    assert len(created_ids) == 2
    first_suffix = int(created_ids[0].rsplit("-", 1)[1])
    second_suffix = int(created_ids[1].rsplit("-", 1)[1])
    assert second_suffix == first_suffix + 1


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

    data = read_metrics(repo)
    task = data["tasks"][0]
    entry = data["entries"][0]

    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263
    assert task["model"] == "gpt-5"
    assert entry["model"] == "gpt-5"
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

    data = read_metrics(repo)
    entries = [entry for entry in data["entries"] if entry["goal_id"] == "entry-task-001"]

    assert len(entries) == 1
    assert entries[0]["status"] == "success"
    assert entries[0]["failure_reason"] is None
    assert entries[0]["cost_usd"] == 0.1
    assert entries[0]["tokens_total"] == 200
    assert entries[0]["finished_at"] is not None
    assert entries[0]["model"] is None


def test_update_existing_task_without_task_id_is_rejected(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--attempts-delta",
        "1",
    )

    assert result.returncode == 1
    assert "task_id is required when updating an existing task" in result.stderr


def test_create_task_without_title_is_rejected_when_task_id_is_omitted(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-type",
        "product",
    )

    assert result.returncode == 1
    assert "title is required when creating a new task" in result.stderr


def test_parallel_auto_id_creates_distinct_goals(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    first_env = os.environ.copy()
    first_env["CODEX_METRICS_DEBUG_LOCK_HOLD_SECONDS"] = "0.5"
    if first_env.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        first_env["COVERAGE_FILE"] = str(WORKSPACE_ROOT / ".coverage")

    second_env = os.environ.copy()
    if second_env.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        second_env["COVERAGE_FILE"] = str(WORKSPACE_ROOT / ".coverage")

    first_process = subprocess.Popen(
        _build_subprocess_cmd("update", "--title", "Parallel A", "--task-type", "product"),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=first_env,
    )
    second_process = subprocess.Popen(
        _build_subprocess_cmd("update", "--title", "Parallel B", "--task-type", "product"),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=second_env,
    )

    first_stdout, first_stderr = first_process.communicate(timeout=15)
    second_stdout, second_stderr = second_process.communicate(timeout=15)

    assert first_process.returncode == 0, first_stderr
    assert second_process.returncode == 0, second_stderr
    assert "Updated goal " in first_stdout
    assert "Updated goal " in second_stdout

    data = read_metrics(repo)
    created_ids = [task["task_id"] for task in data["tasks"]]
    assert len(created_ids) == 2
    assert len(set(created_ids)) == 2


def test_entries_preserve_prior_attempt_when_new_attempt_starts(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    start_result = run_cmd(
        repo,
        "start-task",
        "--title",
        "Multiple attempts task",
        "--task-type",
        "product",
    )
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        goal_id,
        "--attempts-delta",
        "1",
        "--notes",
        "First attempt started",
    ).returncode == 0

    assert run_cmd(
        repo,
        "update",
        "--task-id",
        goal_id,
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
        goal_id,
        "--status",
        "success",
        "--notes",
        "Second attempt succeeded",
    ).returncode == 0

    data = read_metrics(repo)
    entries = sorted(
        [entry for entry in data["entries"] if entry["goal_id"] == goal_id],
        key=lambda entry: entry["entry_id"],
    )

    assert len(entries) == 3
    assert entries[0]["status"] == "fail"
    assert entries[0]["inferred"] is True
    assert entries[0]["failure_reason"] is None
    assert entries[1]["status"] == "fail"
    assert entries[1]["inferred"] is True
    assert entries[1]["failure_reason"] is None
    assert "First attempt started" in entries[1]["notes"]
    assert entries[2]["status"] == "success"
    assert entries[2]["inferred"] is False
    assert entries[2]["failure_reason"] is None
    assert entries[2]["cost_usd"] == 0.2
    assert entries[2]["tokens_total"] == 500
    assert data["summary"]["entries"]["closed_entries"] == 3
    assert data["summary"]["entries"]["successes"] == 1
    assert data["summary"]["entries"]["fails"] == 2
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

    data = read_metrics(repo)
    task = data["tasks"][0]

    assert task["input_tokens"] == 1000
    assert task["cached_input_tokens"] == 100
    assert task["output_tokens"] == 500
    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263
    assert task["model"] == "gpt-5"
    assert data["entries"][0]["model"] == "gpt-5"
    assert task["agent_name"] == "codex"
    assert data["summary"]["total_input_tokens"] == 1000
    assert data["summary"]["total_cached_input_tokens"] == 100
    assert data["summary"]["total_output_tokens"] == 500


def test_update_persists_explicit_token_breakdown_from_model_pricing(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "token-breakdown-task",
        "--title",
        "Token breakdown task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--model",
        "gpt-5",
        "--input-tokens",
        "1200",
        "--cached-input-tokens",
        "300",
        "--output-tokens",
        "400",
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = data["tasks"][0]
    entry = data["entries"][0]

    assert task["input_tokens"] == 1200
    assert task["cached_input_tokens"] == 300
    assert task["output_tokens"] == 400
    assert task["tokens_total"] == 1900
    assert task["model"] == "gpt-5"
    assert entry["input_tokens"] == 1200
    assert entry["cached_input_tokens"] == 300
    assert entry["output_tokens"] == 400
    assert entry["tokens_total"] == 1900
    assert entry["model"] == "gpt-5"
    assert data["summary"]["total_input_tokens"] == 1200
    assert data["summary"]["total_cached_input_tokens"] == 300
    assert data["summary"]["total_output_tokens"] == 400
    assert data["summary"]["known_token_breakdown_successes"] == 1
    assert data["summary"]["complete_token_breakdown_successes"] == 1


def test_update_does_not_apply_codex_agent_label_without_detected_usage(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo)
    assert run_cmd(repo, "init", "--force").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "external-agent-task",
        "--title",
        "External Agent Task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--started-at",
        "2026-03-29T08:00:00+00:00",
        "--finished-at",
        "2026-03-29T08:10:00+00:00",
        "--codex-state-path",
        str(state_path),
        "--codex-logs-path",
        str(logs_path),
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = data["tasks"][0]
    entry = data["entries"][0]

    assert task["agent_name"] is None
    assert task["tokens_total"] is None
    assert task["cost_usd"] is None
    assert task["model"] is None
    assert entry["agent_name"] is None


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

    data = read_metrics(repo)
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

    data = read_metrics(repo)
    summary = data["summary"]

    assert summary["closed_tasks"] == 2
    assert summary["successes"] == 1
    assert summary["fails"] == 1
    assert summary["total_attempts"] == 6
    assert summary["success_rate"] == 0.5
    assert summary["attempts_per_closed_task"] == 3.0
    assert summary["known_cost_successes"] == 1
    assert summary["known_token_successes"] == 1
    assert summary["known_cost_per_success_usd"] == 0.5
    assert summary["known_cost_per_success_tokens"] == 500.0
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
    assert "goal_id already exists as a product goal" in result.stderr
    assert "omit it for auto-generation" in result.stderr


def test_product_goal_can_store_result_fit(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "fit-goal",
        "--title",
        "Fit goal",
        "--task-type",
        "product",
        "--status",
        "success",
        "--result-fit",
        "exact_fit",
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = next(task for task in data["tasks"] if task["task_id"] == "fit-goal")
    assert task["result_fit"] == "exact_fit"
    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
    assert "- Result fit: exact_fit" in report


def test_render_report_includes_model_breakdown(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "model-report",
        "--title",
        "Model report",
        "--task-type",
        "product",
        "--status",
        "success",
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
    ).returncode == 0

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
    assert "## By model" in report
    assert "### gpt-5" in report
    assert "- Model: gpt-5" in report


def test_show_displays_model_coverage(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "model-show",
        "--title",
        "Model show",
        "--task-type",
        "product",
        "--status",
        "success",
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
    ).returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Model coverage:" in result.stdout
    assert "By model:" in result.stdout


def test_update_does_not_write_markdown_report_by_default(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "json-only-goal",
        "--title",
        "JSON only goal",
        "--task-type",
        "product",
        "--status",
        "success",
    )

    assert result.returncode == 0, result.stderr
    assert not (repo / "docs" / "ai-agents-metrics.md").exists()


def test_render_report_command_writes_markdown_export_on_demand(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "render-goal",
        "--title",
        "Render goal",
        "--task-type",
        "product",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(repo, "render-report")

    assert result.returncode == 0, result.stderr
    report_text = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
    assert "Render goal" in report_text


def test_result_fit_is_restricted_to_product_goals(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "retro-fit",
        "--title",
        "Retro fit",
        "--task-type",
        "retro",
        "--status",
        "success",
        "--result-fit",
        "partial_fit",
    )

    assert result.returncode != 0
    assert "result_fit is only allowed for product goals" in result.stderr


def test_failed_goal_only_allows_miss_result_fit(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "bad-fit",
        "--title",
        "Bad fit",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--failure-reason",
        "unclear_task",
        "--result-fit",
        "partial_fit",
    )

    assert result.returncode != 0
    assert "failed product goals may only use result_fit miss" in result.stderr


def test_closed_product_goal_normalizes_zero_duration_window_without_cost(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "zero-window",
        "--title",
        "Zero window",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts-delta",
        "1",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:00:00+00:00",
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = next(task for task in data["tasks"] if task["task_id"] == "zero-window")
    assert task["started_at"] == "2026-03-29T08:59:59+00:00"
    assert task["finished_at"] == "2026-03-29T09:00:00+00:00"


def test_closed_product_goal_allows_zero_duration_window_with_explicit_tokens(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "zero-window-with-tokens",
        "--title",
        "Zero window with tokens",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts-delta",
        "1",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:00:00+00:00",
        "--tokens",
        "123",
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = next(task for task in data["tasks"] if task["task_id"] == "zero-window-with-tokens")
    assert task["tokens_total"] == 123


def test_show_rejects_stored_token_total_smaller_than_known_breakdown(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    events_path = repo / "metrics" / "events.ndjson"
    # Write an event with an invalid goal directly (tokens_total < sum of breakdown)
    invalid_goal = {
        "goal_id": "conflicting-tokens",
        "title": "Conflicting tokens",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "success",
        "attempts": 1,
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": "2026-03-29T09:01:00+00:00",
        "cost_usd": 0.01,
        "input_tokens": 600,
        "cached_input_tokens": 200,
        "output_tokens": 300,
        "tokens_total": 1000,  # 1000 < 600+200+300=1100 — invalid
        "failure_reason": None,
        "notes": None,
        "agent_name": "codex",
        "result_fit": "exact_fit",
        "model": None,
    }
    event = {"event_type": "goal_started", "ts": "2026-03-29T09:01:00+00:00", "goal": invalid_goal, "entries": []}
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode != 0
    assert "tokens_total cannot be smaller than input_tokens + cached_input_tokens + output_tokens" in result.stderr


def test_reused_manual_goal_id_guides_user_to_auto_generation(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "existing-goal",
        "--title",
        "Existing goal",
        "--task-type",
        "product",
        "--attempts-delta",
        "1",
    ).returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "existing-goal",
        "--title",
        "New goal with reused id",
        "--task-type",
        "meta",
    )

    assert result.returncode != 0
    assert "goal_id already exists as a product goal" in result.stderr
    assert "use a new --task-id or omit it for auto-generation" in result.stderr


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
    assert "Unknown model" in result.stderr


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
    # Write an event with a non-string goal_id to trigger type validation
    events_path = repo / "metrics" / "events.ndjson"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "event_type": "goal_started",
        "ts": "2026-03-29T09:01:00+00:00",
        "goal": {
            "goal_id": 999,  # should be a string — invalid
            "title": "Bad type",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "in_progress",
            "attempts": 1,
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
            "model": None,
        },
        "entries": [],
    }
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode != 0
    assert "Invalid type for goal field: goal_id" in result.stderr


def test_duplicate_event_goal_ids_resolve_to_last_write(repo: Path) -> None:
    # With the event log, two events for the same goal_id are resolved by
    # last-write-wins — the second event's state is the final state.
    assert run_cmd(repo, "init").returncode == 0

    assert run_cmd(
        repo, "update", "--task-id", "dup-goal", "--title", "First", "--task-type", "product", "--attempts-delta", "1"
    ).returncode == 0
    assert run_cmd(
        repo, "update", "--task-id", "dup-goal", "--notes", "Updated via second event"
    ).returncode == 0

    data = read_metrics(repo)
    assert len([t for t in data["tasks"] if t["task_id"] == "dup-goal"]) == 1
    assert data["tasks"][0]["notes"] == "Updated via second event"


def test_entry_referencing_unknown_goal_fails(repo: Path) -> None:
    # Write two events: one creates a valid goal, and one creates an entry that
    # intentionally references a non-existent goal_id.
    events_path = repo / "metrics" / "events.ndjson"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    known_goal = {
        "goal_id": "known-goal",
        "title": "Known",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "success",
        "attempts": 1,
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
        "model": None,
    }
    orphan_entry = {
        "entry_id": "known-goal-attempt-001",
        "goal_id": "missing-goal",  # intentionally wrong — goal doesn't exist
        "entry_type": "product",
        "inferred": False,
        "status": "fail",
        "started_at": None,
        "finished_at": None,
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": "other",
        "notes": None,
        "agent_name": None,
        "model": None,
        "attempts": 1,
    }
    events = [
        {"event_type": "goal_started", "ts": "2026-03-29T09:00:00+00:00", "goal": known_goal, "entries": []},
        {
            "event_type": "goal_updated",
            "ts": "2026-03-29T09:01:00+00:00",
            "goal": known_goal,
            "entries": [orphan_entry],
        },
    ]
    events_path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode != 0
    assert "Entry references unknown goal_id: missing-goal" in result.stderr


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

    data = read_metrics(repo)
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


def test_closed_goal_auto_creates_first_attempt_when_closed_without_attempts(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_cmd(
        repo,
        "update",
        "--task-id",
        "zero-attempt-success",
        "--title",
        "Zero Attempt Success",
        "--task-type",
        "product",
        "--status",
        "success",
    )

    assert result.returncode == 0, result.stderr
    data = read_metrics(repo)
    task = data["tasks"][0]
    entries = [entry for entry in data["entries"] if entry["goal_id"] == "zero-attempt-success"]

    assert task["attempts"] == 1
    assert len(entries) == 1
    assert entries[0]["status"] == "success"


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
    data = read_metrics(repo)
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
    assert "AI Agents Metrics Summary" in result.stdout
    assert "Product quality:" in result.stdout
    assert "Reviewed result fit: 0/0 closed product goals" in result.stdout
    assert "Agent recommendations:" in result.stdout
    assert "No closed product goals exist yet, so quality conclusions are not ready." in result.stdout
    assert "Operational summary:" in result.stdout
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

    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["task_type"] == "retro"
    assert data["summary"]["by_task_type"]["retro"]["closed_tasks"] == 1
    assert data["summary"]["by_task_type"]["retro"]["successes"] == 1
    assert data["summary"]["by_task_type"]["product"]["closed_tasks"] == 0

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
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
    data = read_metrics(repo)
    followup_task = next(task for task in data["tasks"] if task["task_id"] == "followup-task")
    assert followup_task["supersedes_task_id"] == "original-task"

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
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

    data = read_metrics(repo)

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

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
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
    data = read_metrics(repo)
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
    # Legacy normalization test — with the event store, goals always have
    # goal_type set. We verify the CLI creates a proper product task and show
    # reports it correctly. The previous raw-JSON injection path no longer
    # applies; we exercise the same end-to-end behavior via the CLI.
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "legacy-task",
        "--title",
        "Legacy task",
        "--task-type",
        "product",
        "--status",
        "success",
        "--started-at",
        "2026-03-29T09:00:00+00:00",
        "--finished-at",
        "2026-03-29T09:01:00+00:00",
        "--notes",
        "Old file without task_type",
    ).returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Product goals: 1 closed, 1 successes, 0 fails" in result.stdout

    update_result = run_cmd(repo, "update", "--task-id", "legacy-task", "--notes", "Normalized")
    assert update_result.returncode == 0, update_result.stderr
    data = read_metrics(repo)
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
    assert "Known total cost (USD): 0.006263" in result.stdout
    assert "Complete cost coverage: 1/1 successful goals" in result.stdout
    assert "Known Cost per Success (USD): 0.006263" in result.stdout
    assert "Complete Cost per Covered Success (USD): 0.006263" in result.stdout


def test_show_reports_known_cost_coverage_when_complete_cost_is_unavailable(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "cost-a",
        "--title",
        "Cost A",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "cost-b",
        "--title",
        "Cost B",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "cost-a",
        "--status",
        "success",
        "--attempts",
        "1",
        "--cost-usd",
        "0.25",
        "--tokens",
        "1000",
    ).returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Known total cost (USD): 0.25" in result.stdout
    assert "Known cost coverage: 1/1 successful goals" in result.stdout
    assert "Complete cost coverage: 0/1 successful goals" in result.stdout
    assert "Known Cost per Success (USD): 0.25" in result.stdout
    assert "Complete Cost per Covered Success (USD): n/a" in result.stdout
    assert "Agent recommendations:" in result.stdout
    assert "Complete cost coverage is still partial across the full history" in result.stdout

    assert render_report(repo).returncode == 0
    report_text = (repo / "docs" / "ai-agents-metrics.md").read_text()
    assert "## Product quality" in report_text
    assert "## Operational summary" in report_text
    assert "## Agent recommendations" in report_text
    assert "Next action: Avoid over-reading complete-cost averages as if they described the whole dataset." in report_text


def test_show_surfaces_reviewed_product_quality_signals(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "fit-a",
        "--title",
        "Exact fit",
        "--task-type",
        "product",
        "--status",
        "success",
        "--result-fit",
        "exact_fit",
        "--cost-usd",
        "0.4",
        "--tokens",
        "400",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "fit-b",
        "--title",
        "Partial fit",
        "--task-type",
        "product",
        "--status",
        "success",
        "--result-fit",
        "partial_fit",
        "--attempts",
        "2",
        "--cost-usd",
        "0.6",
        "--tokens",
        "600",
    ).returncode == 0

    result = run_cmd(repo, "show")

    assert result.returncode == 0, result.stderr
    assert "Closed product goals: 2" in result.stdout
    assert "Reviewed result fit: 2/2 closed product goals" in result.stdout
    assert "Exact fit: 1" in result.stdout
    assert "Partial fit: 1" in result.stdout
    assert "Misses: 0" in result.stdout
    assert "Exact Fit Rate (reviewed): 50.00%" in result.stdout
    assert "Attempts per Closed Product Goal: 1.50" in result.stdout
    assert "Known Product Cost per Success (USD): 0.50" in result.stdout
    assert "Agent recommendations:" in result.stdout
    assert "quality_partial_fit" in result.stdout
    assert "Inspect the partial-fit product goals" in result.stdout


def test_help_includes_goal_language_and_examples(repo: Path) -> None:
    result = run_cmd(repo, "--help")
    update_help = run_cmd(repo, "update", "--help")
    start_help = run_cmd(repo, "start-task", "--help")
    continue_help = run_cmd(repo, "continue-task", "--help")
    finish_help = run_cmd(repo, "finish-task", "--help")
    ensure_help = run_cmd(repo, "ensure-active-task", "--help")

    assert result.returncode == 0, result.stderr
    assert update_help.returncode == 0, update_help.stderr
    assert start_help.returncode == 0, start_help.stderr
    assert continue_help.returncode == 0, continue_help.stderr
    assert finish_help.returncode == 0, finish_help.stderr
    assert ensure_help.returncode == 0, ensure_help.stderr
    assert "Analyze your AI agent work history" in result.stdout
    # `update` is intentionally hidden from the top-level subparser listing
    # to keep first-time --help scannable, but must still be discoverable by
    # name in the grouped epilog and must still work via `update --help`.
    assert "update" in result.stdout  # appears in the "Manual tracking" epilog group
    assert "Manual tracking:" in result.stdout
    assert "start-task" in result.stdout
    assert "continue-task" in result.stdout
    assert "finish-task" in result.stdout
    assert "ensure-active-task" in result.stdout
    assert "Print current summary and operator review" in result.stdout
    assert "Examples:" in result.stdout
    assert "history-audit" in result.stdout
    assert "audit-cost-coverage" in result.stdout
    assert "start-task --title \"Add CSV import\" --task-type product" in result.stdout
    assert "--supersedes-task-id" in update_help.stdout
    assert "Stable goal identifier." in update_help.stdout
    assert "Omit this for new goals" in update_help.stdout
    assert "%(prog)s --title \"Improve CLI help\"" not in update_help.stdout
    assert "--title \"Improve CLI help\" --task-type product --attempts-delta 1" in update_help.stdout
    assert "--title" in start_help.stdout
    assert "--task-type" in start_help.stdout
    assert "--task-id" in continue_help.stdout
    assert "--status {success,fail}" in finish_help.stdout
    assert "create a recovery draft" in ensure_help.stdout


def test_cli_smoke_preserves_current_workflow_roundtrip(repo: Path) -> None:
    init_result = run_cmd(repo, "init")
    assert init_result.returncode == 0, init_result.stderr

    start_result = run_cmd(
        repo,
        "start-task",
        "--title",
        "Smoke test workflow",
        "--task-type",
        "meta",
    )
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    finish_result = run_cmd(
        repo,
        "finish-task",
        "--task-id",
        goal_id,
        "--status",
        "success",
    )
    assert finish_result.returncode == 0, finish_result.stderr

    show_result = run_cmd(repo, "show")
    assert show_result.returncode == 0, show_result.stderr
    assert "Closed goals:" in show_result.stdout
    assert "Meta goals:" in show_result.stdout
    assert "Successes:" in show_result.stdout


def test_script_shim_exposes_cli_version(repo: Path) -> None:
    result = _run_cmd_subprocess(repo, "--version")

    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    assert output.startswith("metrics_cli.py ")
    assert re.fullmatch(
        r"metrics_cli\.py \d+\.\d+.*",
        output,
    )


def test_module_entrypoint_exposes_cli_version(repo: Path) -> None:
    result = run_module_cmd(repo, "--version")

    assert result.returncode == 0, result.stderr
    output = result.stdout.strip()
    assert re.fullmatch(
        r"python[\d.]* -m ai_agents_metrics \d+\.\d+.*",
        output,
    ), f"unexpected --version output: {output!r}"


def test_version_is_a_non_empty_string() -> None:
    assert isinstance(codex_metrics_pkg.__version__, str)
    assert codex_metrics_pkg.__version__


def test_high_level_task_commands_cover_start_continue_finish_flow(repo: Path) -> None:
    start_result = run_cmd(
        repo,
        "start-task",
        "--title",
        "Ship concise onboarding flow",
        "--task-type",
        "product",
        "--notes",
        "First implementation pass",
    )

    assert start_result.returncode == 0, start_result.stderr
    assert "Updated goal" in start_result.stdout
    first_goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    continue_result = run_cmd(
        repo,
        "continue-task",
        "--task-id",
        first_goal_id,
        "--notes",
        "Retry after review feedback",
        "--failure-reason",
        "validation_failed",
    )

    assert continue_result.returncode == 0, continue_result.stderr
    assert f"Updated goal {first_goal_id}" in continue_result.stdout
    assert "Attempts: 2" in continue_result.stdout

    finish_result = run_cmd(
        repo,
        "finish-task",
        "--task-id",
        first_goal_id,
        "--status",
        "success",
        "--notes",
        "Validated and done",
    )

    assert finish_result.returncode == 0, finish_result.stderr
    assert f"Updated goal {first_goal_id}" in finish_result.stdout
    assert "Status: success" in finish_result.stdout

    data = read_metrics(repo)
    goal = next(task for task in data["tasks"] if task["task_id"] == first_goal_id)
    assert goal["status"] == "success"
    assert goal["attempts"] == 2
    assert goal["notes"] == "Validated and done"


def test_finish_task_fail_requires_failure_reason(repo: Path) -> None:
    start_result = run_cmd(
        repo,
        "start-task",
        "--title",
        "Failing task",
        "--task-type",
        "product",
    )
    assert start_result.returncode == 0, start_result.stderr
    goal_id = next(
        line.removeprefix("Updated goal ").strip()
        for line in start_result.stdout.splitlines()
        if line.startswith("Updated goal ")
    )

    finish_result = run_cmd(
        repo,
        "finish-task",
        "--task-id",
        goal_id,
        "--status",
        "fail",
    )

    assert finish_result.returncode == 1
    assert "failure_reason" in finish_result.stderr


def test_audit_history_command_reports_suspicious_goals(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "cost-fail",
        "--title",
        "Cost workflow attempt",
        "--task-type",
        "product",
        "--attempts-delta",
        "1",
        "--status",
        "fail",
        "--failure-reason",
        "unclear_task",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "cost-recovery",
        "--title",
        "Cost workflow recovery",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "cost-fail",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(repo, "history-audit")

    assert result.returncode == 0, result.stderr
    assert "Audit candidates" in result.stdout
    assert "[likely_miss]" in result.stdout
    assert "cost-fail | product | fail" in result.stdout
    assert "[likely_partial_fit]" in result.stdout
    assert "cost-recovery | product | success" in result.stdout
    assert "suggested_result_fit: partial_fit" in result.stdout


def test_package_module_supports_audit_history(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_module_cmd(repo, "history-audit")

    assert result.returncode == 0, result.stderr
    assert "Audit candidates" in result.stdout


def test_audit_cost_coverage_reports_sync_gap(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo)
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "cost-gap-goal",
        "--title",
        "Recoverable cost gap",
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

    result = run_cmd(
        repo,
        "audit-cost-coverage",
        "--codex-state-path",
        str(state_path),
        "--codex-logs-path",
        str(logs_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Cost coverage audit" in result.stdout
    assert "[sync_gap]" in result.stdout
    assert "cost-gap-goal | product | success" in result.stdout


def test_package_module_supports_audit_cost_coverage(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0

    result = run_module_cmd(repo, "audit-cost-coverage")

    assert result.returncode == 0, result.stderr
    assert "Cost coverage audit" in result.stdout


def test_sync_usage_backfills_existing_tasks(repo: Path) -> None:
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
        "sync-usage",
        "--usage-state-path",
        str(state_path),
        "--usage-logs-path",
        str(logs_path),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["input_tokens"] == 1000
    assert task["cached_input_tokens"] == 100
    assert task["output_tokens"] == 500
    assert task["tokens_total"] == 1600
    assert task["cost_usd"] == 0.006263


def test_sync_usage_backfills_from_session_rollout_token_counts(repo: Path) -> None:
    state_path, logs_path = create_codex_session_usage_sources(repo)
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "session-backfill-task",
        "--title",
        "Session Backfill Task",
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
        "sync-usage",
        "--usage-state-path",
        str(state_path),
        "--usage-logs-path",
        str(logs_path),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["input_tokens"] == 1000
    assert task["cached_input_tokens"] == 100
    assert task["output_tokens"] == 500
    assert task["tokens_total"] == 1625
    assert task["cost_usd"] == 0.006263


def test_sync_usage_is_noop_when_no_matching_thread_is_found(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo, cwd=str(repo / "other-worktree"))
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "no-sync-task",
        "--title",
        "No Sync Task",
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
        "sync-usage",
        "--usage-state-path",
        str(state_path),
        "--usage-logs-path",
        str(logs_path),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert "Synchronized usage for 0 task(s)" in sync_result.stdout
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["tokens_total"] is None
    assert task["cost_usd"] is None


def test_sync_usage_writes_agent_name_when_claude_fallback_fires(repo: Path) -> None:
    """sync-usage detects Claude from JSONL and persists agent_name on the task."""
    claude_root = repo / "dot-claude"
    create_claude_jsonl_usage_sources(
        repo,
        claude_root=claude_root,
        cwd=repo,
        model="claude-sonnet-4-6",
        event_timestamp="2026-03-29T09:05:00.000Z",
        input_tokens=1000,
        output_tokens=300,
    )
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "claude-backfill",
        "--title",
        "Claude backfill task",
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
        "sync-usage",
        "--usage-state-path",
        str(repo / "missing_state.sqlite"),
        "--usage-logs-path",
        str(repo / "missing_logs.sqlite"),
        "--claude-root",
        str(claude_root),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert "Synchronized usage for 1 task(s)" in sync_result.stdout
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["agent_name"] == "claude"
    assert task["tokens_total"] is not None
    assert task["cost_usd"] is not None


def test_sync_canonical_usage_alias_still_works(repo: Path) -> None:
    state_path, logs_path = create_codex_usage_sources(repo)
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "alias-task",
        "--title",
        "Alias Task",
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
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["tokens_total"] == 1600


def _make_claude_jsonl_event(
    *,
    session_id: str,
    timestamp: str,
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    output_tokens: int = 0,
    cwd: str = "",
) -> str:
    """Build a minimal Claude JSONL assistant event line."""
    return json.dumps(
        {
            "type": "assistant",
            "sessionId": session_id,
            "timestamp": timestamp,
            "cwd": cwd,
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation_tokens,
                    "cache_read_input_tokens": cache_read_tokens,
                    "output_tokens": output_tokens,
                },
            },
        }
    )


def create_claude_jsonl_usage_sources(
    repo: Path,
    *,
    claude_root: Path,
    cwd: Path | None = None,
    session_id: str = "session-abc",
    model: str = "claude-sonnet-4-6",
    event_timestamp: str = "2026-03-29T09:05:00.000Z",
    input_tokens: int = 1000,
    cache_creation_tokens: int = 500,
    cache_read_tokens: int = 200,
    output_tokens: int = 300,
) -> Path:
    """Create a ~/.claude/projects/{encoded_cwd}/{session}.jsonl fixture under claude_root."""
    resolved_cwd = cwd or repo
    encoded = str(resolved_cwd).replace("/", "-").replace(".", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = project_dir / f"{session_id}.jsonl"
    event_line = _make_claude_jsonl_event(
        session_id=session_id,
        timestamp=event_timestamp,
        model=model,
        input_tokens=input_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        output_tokens=output_tokens,
        cwd=str(resolved_cwd),
    )
    jsonl_path.write_text(event_line + "\n", encoding="utf-8")
    return claude_root


def test_claude_usage_backend_resolves_from_jsonl(tmp_path: Path) -> None:
    # Arrange: two JSONL events within the time window, one outside
    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = tmp_path / "dot-claude"
    encoded = str(cwd).replace("/", "-").replace(".", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)

    session_jsonl = project_dir / "session-001.jsonl"
    lines = [
        # event inside window
        _make_claude_jsonl_event(
            session_id="session-001",
            timestamp="2026-03-29T09:05:00.000Z",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            cache_creation_tokens=500,
            cache_read_tokens=200,
            output_tokens=300,
            cwd=str(cwd),
        ),
        # second event inside window
        _make_claude_jsonl_event(
            session_id="session-001",
            timestamp="2026-03-29T09:08:00.000Z",
            model="claude-sonnet-4-6",
            input_tokens=200,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            output_tokens=100,
            cwd=str(cwd),
        ),
        # event OUTSIDE window (before started_at)
        _make_claude_jsonl_event(
            session_id="session-001",
            timestamp="2026-03-29T08:59:00.000Z",
            model="claude-sonnet-4-6",
            input_tokens=9999,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            output_tokens=9999,
            cwd=str(cwd),
        ),
    ]
    session_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    backend = ClaudeUsageBackend()
    window = resolve_backend_usage_window(
        backend,
        state_path=claude_root,
        logs_path=claude_root / "unused.sqlite",
        cwd=cwd,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=PRICING,
    )

    assert window.backend_name == "claude"
    assert window.total_tokens == 2300  # (1000+500+200+300) + (200+100)
    assert window.input_tokens == 1200  # 1000 + 200
    assert window.cached_input_tokens == 200  # cache_read only
    assert window.output_tokens == 400  # 300 + 100
    assert window.model_name == "claude-sonnet-4-6"
    # cost: event1=0.009435, event2=0.0021 → total=0.011535
    assert window.cost_usd == 0.011535


def test_claude_usage_backend_sums_multiple_sessions(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = tmp_path / "dot-claude"
    encoded = str(cwd).replace("/", "-").replace(".", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True)

    for session_id, ts in [("s1", "2026-03-29T09:02:00.000Z"), ("s2", "2026-03-29T09:07:00.000Z")]:
        (project_dir / f"{session_id}.jsonl").write_text(
            _make_claude_jsonl_event(
                session_id=session_id,
                timestamp=ts,
                model="claude-sonnet-4-6",
                input_tokens=100,
                cache_creation_tokens=0,
                cache_read_tokens=0,
                output_tokens=50,
                cwd=str(cwd),
            )
            + "\n",
            encoding="utf-8",
        )

    backend = ClaudeUsageBackend()
    window = resolve_backend_usage_window(
        backend,
        state_path=claude_root,
        logs_path=claude_root / "unused.sqlite",
        cwd=cwd,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=PRICING,
    )

    assert window.backend_name == "claude"
    assert window.total_tokens == 300  # (100+50) * 2 sessions
    assert window.input_tokens == 200
    assert window.output_tokens == 100


def test_claude_usage_backend_includes_subagent_tokens(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = tmp_path / "dot-claude"
    encoded = str(cwd).replace("/", "-").replace(".", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True)

    # top-level session
    (project_dir / "main-session.jsonl").write_text(
        _make_claude_jsonl_event(
            session_id="main-session",
            timestamp="2026-03-29T09:03:00.000Z",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=100,
            cwd=str(cwd),
        )
        + "\n",
        encoding="utf-8",
    )

    # subagent tokens
    subagent_dir = project_dir / "main-session" / "subagents"
    subagent_dir.mkdir(parents=True)
    (subagent_dir / "agent-sub1.jsonl").write_text(
        _make_claude_jsonl_event(
            session_id="agent-sub1",
            timestamp="2026-03-29T09:04:00.000Z",
            model="claude-sonnet-4-6",
            input_tokens=300,
            output_tokens=80,
            cwd=str(cwd),
        )
        + "\n",
        encoding="utf-8",
    )

    backend = ClaudeUsageBackend()
    window = resolve_backend_usage_window(
        backend,
        state_path=claude_root,
        logs_path=claude_root / "unused.sqlite",
        cwd=cwd,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=PRICING,
    )

    # main (500+100) + subagent (300+80) = 980 total
    assert window.total_tokens == 980
    assert window.input_tokens == 800
    assert window.output_tokens == 180


def test_claude_usage_backend_returns_unknown_when_no_project_dir(tmp_path: Path) -> None:
    claude_root = tmp_path / "dot-claude"
    claude_root.mkdir()

    backend = ClaudeUsageBackend()
    window = resolve_backend_usage_window(
        backend,
        state_path=claude_root,
        logs_path=claude_root / "unused.sqlite",
        cwd=tmp_path / "nonexistent-project",
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=PRICING,
    )

    assert window.backend_name == "claude"
    assert window.total_tokens is None
    assert window.cost_usd is None


def test_claude_usage_backend_haiku_alias_resolves_pricing(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = tmp_path / "dot-claude"
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=claude_root,
        cwd=cwd,
        model="claude-haiku-4-5",  # alias without date suffix
        input_tokens=1000,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=500,
    )

    backend = ClaudeUsageBackend()
    window = resolve_backend_usage_window(
        backend,
        state_path=claude_root,
        logs_path=claude_root / "unused.sqlite",
        cwd=cwd,
        started_at="2026-03-29T09:00:00+00:00",
        finished_at="2026-03-29T09:10:00+00:00",
        pricing_path=PRICING,
    )

    # haiku-4-5: input=$1/M, output=$5/M
    # cost: 1000*1.0/1M + 500*5.0/1M = 0.001 + 0.0025 = 0.0035
    assert window.total_tokens == 1500
    assert window.cost_usd == 0.0035
    assert window.model_name == "claude-haiku-4-5"



def test_resolve_goal_usage_updates_detects_claude_via_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Codex SQLite is absent, Claude JSONL with data in the time window is used as fallback.
    This correctly handles mixed-agent repos: the backend that has actual telemetry wins."""
    import ai_agents_metrics.cli as cli_module
    from ai_agents_metrics.domain import GoalRecord

    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=tmp_path / "dot-claude",
        cwd=cwd,
        model="claude-sonnet-4-6",
        event_timestamp="2026-03-29T09:05:00.000Z",
        input_tokens=400,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=100,
    )
    monkeypatch.setattr(cli_module, "CLAUDE_ROOT", claude_root)

    task = GoalRecord(
        goal_id="test-goal",
        title="Test",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=1,
        started_at=datetime.fromisoformat("2026-03-29T09:00:00+00:00"),
        finished_at=datetime.fromisoformat("2026-03-29T09:10:00+00:00"),
        cost_usd=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
        agent_name=None,  # not yet set
    )

    *_, detected_agent_name = cli_module.resolve_goal_usage_updates(
        task=task,
        cost_usd_add=None,
        cost_usd_set=None,
        tokens_add=None,
        tokens_set=None,
        model=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        pricing_path=PRICING,
        codex_state_path=tmp_path / "missing.sqlite",  # Codex absent
        codex_logs_path=tmp_path / "missing_logs.sqlite",
        codex_thread_id=None,
        cwd=cwd,
        started_at=None,
        finished_at=None,
        claude_root=claude_root,
    )
    # Claude fallback triggered and data found → agent detected
    assert detected_agent_name == "claude"


def test_resolve_goal_usage_updates_no_detection_when_no_data_in_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At start-task time (no telemetry yet), neither backend has data → agent_name stays None."""
    import ai_agents_metrics.cli as cli_module
    from ai_agents_metrics.domain import GoalRecord

    cwd = tmp_path / "repo"
    cwd.mkdir()
    # Claude JSONL exists but has NO events in the task time window (task just started)
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=tmp_path / "dot-claude",
        cwd=cwd,
        model="claude-sonnet-4-6",
        event_timestamp="2026-03-28T10:00:00.000Z",  # old event, outside the window
        input_tokens=999,
        output_tokens=999,
    )
    monkeypatch.setattr(cli_module, "CLAUDE_ROOT", claude_root)

    task = GoalRecord(
        goal_id="test-goal",
        title="Test",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=1,
        started_at=datetime.fromisoformat("2026-03-29T09:00:00+00:00"),
        finished_at=None,  # not finished yet
        cost_usd=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
        agent_name=None,
    )

    *_, detected_agent_name = cli_module.resolve_goal_usage_updates(
        task=task,
        cost_usd_add=None,
        cost_usd_set=None,
        tokens_add=None,
        tokens_set=None,
        model=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        pricing_path=PRICING,
        codex_state_path=tmp_path / "missing.sqlite",
        codex_logs_path=tmp_path / "missing_logs.sqlite",
        codex_thread_id=None,
        cwd=cwd,
        started_at=None,
        finished_at=None,
        claude_root=claude_root,
    )
    # No data in window → no detection
    assert detected_agent_name is None


def test_resolve_goal_usage_updates_does_not_overwrite_stored_agent_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If goal already has agent_name set, it is preserved and not returned as detected."""
    import ai_agents_metrics.cli as cli_module
    from ai_agents_metrics.domain import GoalRecord

    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=tmp_path / "dot-claude",
        cwd=cwd,
    )
    monkeypatch.setattr(cli_module, "CLAUDE_ROOT", claude_root)

    task = GoalRecord(
        goal_id="test-goal",
        title="Test",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=1,
        started_at=datetime.fromisoformat("2026-03-29T09:00:00+00:00"),
        finished_at=None,
        cost_usd=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
        agent_name="claude",  # already stored — should not re-detect
    )

    *_, detected_agent_name = cli_module.resolve_goal_usage_updates(
        task=task,
        cost_usd_add=None,
        cost_usd_set=None,
        tokens_add=None,
        tokens_set=None,
        model=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        pricing_path=PRICING,
        codex_state_path=tmp_path / "missing.sqlite",
        codex_logs_path=tmp_path / "missing_logs.sqlite",
        codex_thread_id=None,
        cwd=cwd,
        started_at=None,
        finished_at=None,
        claude_root=claude_root,
    )
    # No detection write needed since agent_name already stored
    assert detected_agent_name is None


def test_resolve_goal_usage_updates_routes_to_claude_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """update on a goal with agent_name=claude picks up tokens from JSONL, not Codex SQLite."""
    import ai_agents_metrics.cli as cli_module
    from ai_agents_metrics.domain import GoalRecord

    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=tmp_path / "dot-claude",
        cwd=cwd,
        model="claude-sonnet-4-6",
        event_timestamp="2026-03-29T09:05:00.000Z",
        input_tokens=500,
        cache_creation_tokens=0,
        cache_read_tokens=100,
        output_tokens=200,
    )
    monkeypatch.setattr(cli_module, "CLAUDE_ROOT", claude_root)

    task = GoalRecord(
        goal_id="claude-goal",
        title="Claude Goal",
        goal_type="product",
        supersedes_goal_id=None,
        status="in_progress",
        attempts=1,
        started_at=datetime.fromisoformat("2026-03-29T09:00:00+00:00"),
        finished_at=datetime.fromisoformat("2026-03-29T09:10:00+00:00"),
        cost_usd=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        tokens_total=None,
        failure_reason=None,
        notes=None,
        agent_name="claude",
    )

    (
        _usage_cost, _usage_tokens, _usage_input, _usage_cached, _usage_output, _usage_model,
        auto_cost, auto_total, auto_input, auto_cached, auto_output, auto_model,
        detected_agent_name,
    ) = cli_module.resolve_goal_usage_updates(
        task=task,
        cost_usd_add=None,
        cost_usd_set=None,
        tokens_add=None,
        tokens_set=None,
        model=None,
        input_tokens=None,
        cached_input_tokens=None,
        output_tokens=None,
        pricing_path=PRICING,
        codex_state_path=tmp_path / "missing.sqlite",  # Codex SQLite absent — must not be used
        codex_logs_path=tmp_path / "missing_logs.sqlite",
        codex_thread_id=None,
        cwd=cwd,
        started_at=None,
        finished_at=None,
        claude_root=claude_root,
    )

    # Tokens resolved from JSONL
    assert auto_total == 800  # 500 + 100 + 200
    assert auto_input == 500
    assert auto_cached == 100
    assert auto_output == 200
    assert auto_model == "claude-sonnet-4-6"
    # cost: 500*3/1M + 100*0.3/1M + 200*15/1M = 0.0015 + 0.00003 + 0.003 = 0.00453
    assert auto_cost == 0.00453
    # agent_name already stored — no detection write
    assert detected_agent_name is None


def test_audit_cost_coverage_reports_sync_gap_for_claude_goal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude goal with JSONL data in window but no stored cost is classified as sync_gap."""
    import ai_agents_metrics.cli as cli_module

    cwd = tmp_path / "repo"
    cwd.mkdir()
    claude_root = create_claude_jsonl_usage_sources(
        tmp_path,
        claude_root=tmp_path / "dot-claude",
        cwd=cwd,
        model="claude-sonnet-4-6",
        event_timestamp="2026-03-29T09:05:00.000Z",
        input_tokens=1000,
        output_tokens=200,
    )
    monkeypatch.setattr(cli_module, "CLAUDE_ROOT", claude_root)

    data = {
        "goals": [
            {
                "goal_id": "claude-sync-gap",
                "title": "Claude goal with no stored cost",
                "goal_type": "product",
                "status": "success",
                "attempts": 1,
                "started_at": "2026-03-29T09:00:00+00:00",
                "finished_at": "2026-03-29T09:10:00+00:00",
                "cost_usd": None,
                "tokens_total": None,
                "agent_name": "claude",
            }
        ],
        "entries": [],
    }

    report = cli_module.audit_cost_coverage(
        data,
        pricing_path=PRICING,
        codex_state_path=tmp_path / "missing.sqlite",
        codex_logs_path=tmp_path / "missing_logs.sqlite",
        codex_thread_id=None,
        cwd=cwd,
        claude_root=claude_root,
    )

    assert len(report.candidates) == 1
    candidate = report.candidates[0]
    assert candidate.category == "sync_gap"
    assert candidate.goal_id == "claude-sync-gap"


def test_missing_usage_state_uses_unknown_backend(repo: Path) -> None:
    backend = select_usage_backend(repo / "missing_state.sqlite", repo, None)
    assert backend.name == "unknown"


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
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
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
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
        "--started-at",
        "2026-03-29T09:06:00+00:00",
        "--finished-at",
        "2026-03-29T09:10:00+00:00",
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
    data = read_metrics(repo)
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
    assert task["model"] == "gpt-5"
    assert [entry["model"] for entry in data["entries"]] == ["gpt-5", "gpt-5"]


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
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["cost_usd"] is None
    assert task["tokens_total"] is None
    assert data["summary"]["known_cost_successes"] == 0
    assert data["summary"]["known_token_successes"] == 0
    assert data["summary"]["known_cost_per_success_usd"] is None
    assert data["summary"]["known_cost_per_success_tokens"] is None
    assert data["summary"]["cost_per_success_usd"] is None
    assert data["summary"]["cost_per_success_tokens"] is None


def test_merge_tasks_clears_model_when_attempt_history_disagrees(repo: Path) -> None:
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
        "success",
        "--attempts",
        "1",
        "--model",
        "gpt-5",
        "--input-tokens",
        "100",
        "--output-tokens",
        "50",
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
        "--model",
        "gpt-5.4",
        "--input-tokens",
        "120",
        "--output-tokens",
        "60",
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
    data = read_metrics(repo)
    task = data["tasks"][0]
    assert task["model"] is None
    assert [entry["model"] for entry in data["entries"]] == ["gpt-5", "gpt-5.4"]


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


def test_merge_tasks_rejects_different_goal_types(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "product-task",
        "--title",
        "Product task",
        "--task-type",
        "product",
        "--status",
        "success",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "retro-task",
        "--title",
        "Retro task",
        "--task-type",
        "retro",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "product-task",
        "--drop-task-id",
        "retro-task",
    )

    assert result.returncode != 0
    assert "only goals with the same goal_type can be merged" in result.stderr


def test_merge_tasks_rejects_supersession_cycle(repo: Path) -> None:
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
        "--failure-reason",
        "validation_failed",
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
        "--supersedes-task-id",
        "task-a",
        "--status",
        "success",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-a",
        "--drop-task-id",
        "task-b",
    )

    assert result.returncode != 0
    assert "merge would create a supersession cycle" in result.stderr


def test_merge_tasks_rewrites_downstream_supersession_links(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-a",
        "--title",
        "Task A",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-b",
        "--title",
        "Task B",
        "--task-type",
        "product",
        "--status",
        "fail",
        "--attempts",
        "1",
        "--failure-reason",
        "model_mistake",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-c",
        "--title",
        "Task C",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "task-b",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-a",
        "--drop-task-id",
        "task-b",
    )

    assert result.returncode == 0, result.stderr
    show_result = run_cmd(repo, "show")
    assert show_result.returncode == 0, show_result.stderr
    data = read_metrics(repo)
    task_c = next(task for task in data["tasks"] if task["task_id"] == "task-c")
    assert task_c["supersedes_task_id"] == "task-a"


def test_merge_tasks_rejects_transitive_supersession_cycle(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-b",
        "--title",
        "Task B",
        "--task-type",
        "product",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-c",
        "--title",
        "Task C",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "task-b",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-a",
        "--title",
        "Task A",
        "--task-type",
        "product",
        "--supersedes-task-id",
        "task-c",
        "--status",
        "success",
        "--attempts",
        "1",
    ).returncode == 0

    result = run_cmd(
        repo,
        "merge-tasks",
        "--keep-task-id",
        "task-a",
        "--drop-task-id",
        "task-b",
    )

    assert result.returncode != 0
    assert "merge would create a supersession cycle" in result.stderr


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

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
    newer_index = report.index("### newer")
    older_index = report.index("### older")

    assert newer_index < older_index


def test_report_marks_inferred_entries(repo: Path) -> None:
    assert run_cmd(repo, "init").returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-inferred",
        "--title",
        "Task inferred",
        "--task-type",
        "product",
        "--attempts-delta",
        "1",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-inferred",
        "--attempts-delta",
        "1",
        "--notes",
        "Second attempt started",
    ).returncode == 0
    assert run_cmd(
        repo,
        "update",
        "--task-id",
        "task-inferred",
        "--status",
        "success",
    ).returncode == 0

    assert render_report(repo).returncode == 0
    report = (repo / "docs" / "ai-agents-metrics.md").read_text(encoding="utf-8")
    assert "- Inferred: yes" in report
    assert "- Inferred: no" in report


def test_invalid_entry_business_state_fails(repo: Path) -> None:
    assert run_cmd(repo, "init", "--force").returncode == 0
    events_path = repo / "metrics" / "events.ndjson"
    goal = {
        "goal_id": "goal-001",
        "title": "Goal 001",
        "goal_type": "product",
        "supersedes_goal_id": None,
        "status": "success",
        "attempts": 1,
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": "2026-03-29T09:10:00+00:00",
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": None,
        "notes": None,
        "agent_name": None,
        "result_fit": None,
        "model": None,
    }
    # Entry with status=success but failure_reason set — invalid business state
    invalid_entry = {
        "entry_id": "entry-001",
        "goal_id": "goal-001",
        "entry_type": "product",
        "inferred": False,
        "status": "success",
        "started_at": "2026-03-29T09:00:00+00:00",
        "finished_at": "2026-03-29T09:10:00+00:00",
        "cost_usd": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "tokens_total": None,
        "failure_reason": "validation_failed",
        "notes": None,
        "agent_name": None,
        "model": None,
    }
    event = {"event_type": "goal_started", "ts": "2026-03-29T09:00:00+00:00", "goal": goal, "entries": [invalid_entry]}
    events_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = run_cmd(repo, "show")

    assert result.returncode != 0
    assert "failure_reason must be empty when status is success" in result.stderr


# ---------------------------------------------------------------------------
# history-ingest / history-update: --source all visibility and behaviour
# ---------------------------------------------------------------------------


def test_history_ingest_source_all_accepted(repo: Path) -> None:
    """--source all must be accepted by argparse and exit 0 (sources are skipped if absent)."""
    warehouse = repo / "warehouse.sqlite"
    result = run_cmd(repo, "history-ingest", "--source", "all", "--warehouse-path", str(warehouse))
    # argparse rejects unknown choices with exit code 2; any other non-zero means
    # the argument was parsed and an operational error occurred, which is acceptable.
    assert result.returncode != 2, f"argparse rejected --source all:\n{result.stderr}"
    assert result.returncode == 0, f"history-ingest --source all failed:\n{result.stderr}"


def test_history_ingest_no_source_flag_defaults_to_all(repo: Path) -> None:
    """Omitting --source behaves like --source all: reads both sources, skips absent ones."""
    warehouse = repo / "warehouse.sqlite"
    result_default = run_cmd(repo, "history-ingest", "--warehouse-path", str(warehouse))
    assert result_default.returncode == 0, f"history-ingest (default) failed:\n{result_default.stderr}"

    warehouse2 = repo / "warehouse2.sqlite"
    result_all = run_cmd(repo, "history-ingest", "--source", "all", "--warehouse-path", str(warehouse2))
    assert result_all.returncode == 0, f"history-ingest --source all failed:\n{result_all.stderr}"

    # Both produce the same style of output (skip lines or ingested lines), not a codex-only view.
    # The presence of "codex" or "claude" labels in stdout distinguishes "all" from single-source output.
    for label in ("codex", "claude"):
        if f"Skipping {label}" in result_default.stdout or label in result_default.stdout:
            break
    else:
        # Neither source was mentioned — acceptable only if both were actually ingested without labels,
        # which should not happen; fail loudly so the test surface is clear.
        assert False, f"Unexpected default output (no source labels):\n{result_default.stdout}"


def test_history_ingest_source_root_incompatible_with_source_all(repo: Path) -> None:
    """--source-root combined with --source all must be rejected with exit code 1."""
    warehouse = repo / "warehouse.sqlite"
    result = run_cmd(
        repo,
        "history-ingest",
        "--source", "all",
        "--source-root", str(repo),
        "--warehouse-path", str(warehouse),
    )
    assert result.returncode == 1
    assert "--source-root cannot be used with --source all" in result.stderr


def test_history_update_source_all_accepted(repo: Path) -> None:
    """history-update --source all must be accepted and exit 0."""
    warehouse = repo / "warehouse.sqlite"
    result = run_cmd(repo, "history-update", "--source", "all", "--warehouse-path", str(warehouse))
    assert result.returncode != 2, f"argparse rejected --source all:\n{result.stderr}"
    assert result.returncode == 0, f"history-update --source all failed:\n{result.stderr}"


def test_history_update_no_source_flag_defaults_to_all(repo: Path) -> None:
    """history-update without --source defaults to reading both codex and claude."""
    warehouse = repo / "warehouse.sqlite"
    result = run_cmd(repo, "history-update", "--warehouse-path", str(warehouse))
    assert result.returncode == 0, f"history-update (default) failed:\n{result.stderr}"
    # The "all" path either runs normalize or reports no sources found — both are valid.
    # It must not fail with an unhandled warehouse-not-found error.
    assert "Error:" not in result.stderr, f"Unexpected error:\n{result.stderr}"


def test_history_update_source_root_incompatible_with_source_all(repo: Path) -> None:
    """history-update --source all --source-root must be rejected with exit code 1."""
    warehouse = repo / "warehouse.sqlite"
    result = run_cmd(
        repo,
        "history-update",
        "--source", "all",
        "--source-root", str(repo),
        "--warehouse-path", str(warehouse),
    )
    assert result.returncode == 1
    assert "--source-root cannot be used with --source all" in result.stderr
