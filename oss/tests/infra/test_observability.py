from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import ai_agents_metrics.observability as observability
from ai_agents_metrics.observability import (
    observability_paths,
    record_cli_invocation_observation,
    record_goal_mutation_observation,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_record_goal_mutation_observation_writes_sqlite_and_debug_log(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"

    record_goal_mutation_observation(
        metrics_path,
        command="start-task",
        previous_task=None,
        current_task={
            "goal_id": "goal-1",
            "title": "Create event log",
            "goal_type": "meta",
            "status": "in_progress",
            "attempts": 1,
            "started_at": "2026-04-02T00:00:00+00:00",
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
            "supersedes_goal_id": None,
        },
    )

    paths = observability_paths(metrics_path)
    assert paths.event_store_path.exists()
    assert paths.debug_log_path.exists()

    with sqlite3.connect(paths.event_store_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events").fetchone()

    assert row is not None
    assert row["event_type"] == "goal_created"
    assert row["command"] == "start-task"
    assert row["goal_id"] == "goal-1"
    payload = json.loads(row["payload_json"])
    assert payload["command"] == "start-task"
    assert payload["changed_fields"] == [
        "attempts",
        "goal_type",
        "started_at",
        "status",
        "title",
    ]
    debug_log = paths.debug_log_path.read_text(encoding="utf-8")
    assert row["event_id"] in debug_log
    assert 'event_type="goal_created"' in debug_log


def test_record_cli_invocation_observation_writes_sqlite_and_debug_log(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"

    record_cli_invocation_observation(
        metrics_path,
        command="show",
        cwd="/tmp/workspace",
        task_id="goal-1",
    )

    paths = observability_paths(metrics_path)
    assert paths.event_store_path.exists()
    assert paths.debug_log_path.exists()

    with sqlite3.connect(paths.event_store_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events").fetchone()

    assert row is not None
    assert row["event_type"] == "cli_invoked"
    assert row["command"] == "show"
    assert row["goal_id"] == "goal-1"
    payload = json.loads(row["payload_json"])
    assert payload["command"] == "show"
    assert payload["cwd"] == "/tmp/workspace"
    assert payload["task_id"] == "goal-1"
    debug_log = paths.debug_log_path.read_text(encoding="utf-8")
    assert row["event_id"] in debug_log
    assert 'event_type="cli_invoked"' in debug_log


def test_record_cli_invocation_observation_redacts_sensitive_payload_values(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"

    record_cli_invocation_observation(
        metrics_path,
        command="update",
        cwd="/tmp/workspace",
        extra_payload={
            "api_key": "sk-test-secret-value-1234567890",
            "notes": "Bearer abcdefghijklmnop",
        },
    )

    paths = observability_paths(metrics_path)
    debug_log = paths.debug_log_path.read_text(encoding="utf-8")
    assert "sk-test-secret-value-1234567890" not in debug_log
    assert "Bearer abcdefghijklmnop" not in debug_log
    assert "[REDACTED]" in debug_log


def test_record_cli_invocation_observation_best_effort_on_store_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"
    monkeypatch.setattr(observability, "_store_event", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))

    record_cli_invocation_observation(metrics_path, command="show", cwd="/tmp/workspace")

    paths = observability_paths(metrics_path)
    assert not paths.event_store_path.exists()
    debug_log = paths.debug_log_path.read_text(encoding="utf-8")
    assert 'event_type="observability_write_failed"' in debug_log
    assert 'command="show"' in debug_log
