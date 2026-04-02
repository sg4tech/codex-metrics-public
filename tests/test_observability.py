from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from codex_metrics.observability import observability_paths, record_goal_mutation_observation


def test_record_goal_mutation_observation_writes_sqlite_and_debug_log(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "codex_metrics.json"

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
    assert "event_type=\"goal_created\"" in debug_log
