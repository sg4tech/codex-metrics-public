from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_history_ingest import run_cmd

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ABS_SCRIPT = WORKSPACE_ROOT / "scripts" / "update_codex_metrics.py"
ABS_SRC = WORKSPACE_ROOT / "src"
SRC = WORKSPACE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_metrics.domain import default_metrics, recompute_summary
from codex_metrics.retro_timeline import build_retro_timeline_report, derive_retro_timeline


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pricing").mkdir(parents=True, exist_ok=True)

    script_target = tmp_path / "scripts" / "update_codex_metrics.py"
    script_target.write_text(ABS_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copytree(ABS_SRC, tmp_path / "src")

    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, text=True, capture_output=True, check=True)
    return tmp_path


def _build_metrics_data() -> dict[str, object]:
    data = default_metrics()
    data["goals"] = [
        {
            "goal_id": "prod-1",
            "title": "Before exact",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-04-01T09:00:00+00:00",
            "finished_at": "2026-04-01T09:05:00+00:00",
            "cost_usd": 1.0,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": 1000,
            "failure_reason": None,
            "notes": None,
            "result_fit": "exact_fit",
            "model": None,
        },
        {
            "goal_id": "prod-2",
            "title": "Before partial",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 2,
            "started_at": "2026-04-01T10:00:00+00:00",
            "finished_at": "2026-04-01T10:10:00+00:00",
            "cost_usd": 3.0,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": 3000,
            "failure_reason": None,
            "notes": None,
            "result_fit": "partial_fit",
            "model": None,
        },
        {
            "goal_id": "prod-3",
            "title": "After exact",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "success",
            "attempts": 1,
            "started_at": "2026-04-01T12:00:00+00:00",
            "finished_at": "2026-04-01T12:05:00+00:00",
            "cost_usd": 0.5,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": 500,
            "failure_reason": None,
            "notes": None,
            "result_fit": "exact_fit",
            "model": None,
        },
        {
            "goal_id": "prod-4",
            "title": "After fail",
            "goal_type": "product",
            "supersedes_goal_id": None,
            "status": "fail",
            "attempts": 3,
            "started_at": "2026-04-01T13:00:00+00:00",
            "finished_at": "2026-04-01T13:20:00+00:00",
            "cost_usd": 2.0,
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "tokens_total": 2000,
            "failure_reason": "validation_failed",
            "notes": None,
            "result_fit": "miss",
            "model": None,
        },
    ]
    recompute_summary(data)
    return data


def _build_normalized_history_db(warehouse_path: Path, cwd: Path) -> None:
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(warehouse_path) as conn:
        conn.execute(
            """
            CREATE TABLE normalized_threads (
                thread_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                cwd TEXT,
                model_provider TEXT,
                model TEXT,
                title TEXT,
                archived INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                rollout_path TEXT,
                session_count INTEGER NOT NULL,
                event_count INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                log_count INTEGER NOT NULL,
                first_seen_at TEXT,
                last_seen_at TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE normalized_messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT,
                session_path TEXT NOT NULL,
                source_path TEXT NOT NULL,
                event_index INTEGER NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO normalized_threads (
                thread_id, source_path, cwd, model_provider, model, title, archived, created_at, updated_at,
                rollout_path, session_count, event_count, message_count, log_count, first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-1",
                "source-1.sqlite",
                str(cwd),
                "openai",
                "gpt-5.4",
                "retro thread",
                0,
                1,
                2,
                "rollout-1.jsonl",
                1,
                3,
                3,
                0,
                "2026-04-01T10:00:00.000Z",
                "2026-04-01T12:00:00.000Z",
                json.dumps({"thread_id": "thread-1"}, sort_keys=True),
            ),
        )
        conn.executemany(
            """
            INSERT INTO normalized_messages (
                message_id, thread_id, session_path, source_path, event_index, message_index, role, text, timestamp, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "msg-1",
                    "thread-1",
                    "session-1.jsonl",
                    "source-1.jsonl",
                    1,
                    0,
                    "assistant",
                    "Сделал. Добавил ретро в [docs/retros/2026-04-03-message-level-retro.md](docs/retros/2026-04-03-message-level-retro.md)",
                    "2026-04-01T11:00:00.000Z",
                    json.dumps({"message_id": "msg-1"}, sort_keys=True),
                ),
                (
                    "msg-2",
                    "thread-1",
                    "session-1.jsonl",
                    "source-1.jsonl",
                    2,
                    1,
                    "user",
                    "This one should not count even if it mentions docs/retros/2026-04-03-user-message.md",
                    "2026-04-01T11:05:00.000Z",
                    json.dumps({"message_id": "msg-2"}, sort_keys=True),
                ),
                (
                    "msg-3",
                    "thread-1",
                    "session-1.jsonl",
                    "source-1.jsonl",
                    3,
                    2,
                    "assistant",
                    "Duplicate retro link should not create a second anchor [docs/retros/2026-04-03-message-level-retro.md](docs/retros/2026-04-03-message-level-retro.md)",
                    "2026-04-01T11:06:00.000Z",
                    json.dumps({"message_id": "msg-3"}, sort_keys=True),
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO normalized_threads (
                thread_id, source_path, cwd, model_provider, model, title, archived, created_at, updated_at,
                rollout_path, session_count, event_count, message_count, log_count, first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-ignored",
                "source-ignored.sqlite",
                "/Users/viktor/OtherProject",
                "openai",
                "gpt-5.4",
                "ignored thread",
                0,
                1,
                2,
                "rollout-ignored.jsonl",
                1,
                1,
                1,
                0,
                "2026-04-01T11:00:00.000Z",
                "2026-04-01T11:00:00.000Z",
                json.dumps({"thread_id": "thread-ignored"}, sort_keys=True),
            ),
        )
        conn.execute(
            """
            INSERT INTO normalized_messages (
                message_id, thread_id, session_path, source_path, event_index, message_index, role, text, timestamp, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-ignored",
                "thread-ignored",
                "session-ignored.jsonl",
                "source-ignored.jsonl",
                1,
                0,
                "assistant",
                "This message mentions [docs/retros/2026-04-03-ignored-retro.md](docs/retros/2026-04-03-ignored-retro.md)",
                "2026-04-01T11:10:00.000Z",
                json.dumps({"message_id": "msg-ignored"}, sort_keys=True),
            ),
        )


def test_build_retro_timeline_report_creates_before_after_windows(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"
    warehouse_path = tmp_path / "metrics" / ".codex-metrics" / "retro.sqlite"
    _build_normalized_history_db(warehouse_path, tmp_path)
    report = build_retro_timeline_report(
        _build_metrics_data(),
        warehouse_path=warehouse_path,
        cwd=tmp_path,
        metrics_path=metrics_path,
        window_size=2,
    )

    assert len(report.events) == 1
    assert len(report.windows) == 2
    assert len(report.deltas) == 1

    record = report.records[0]
    assert record.event.message_id == "msg-1"
    assert record.event.source_kind == "message"
    assert record.event.retro_file_path == "docs/retros/2026-04-03-message-level-retro.md"
    assert record.event.title == "message level retro"
    assert record.before_window.product_goals_closed == 2
    assert record.after_window.product_goals_closed == 2
    assert record.before_window.exact_fit_rate == 0.5
    assert record.after_window.exact_fit_rate == 0.5
    assert record.before_window.attempts_per_closed_product_goal == 1.5
    assert record.after_window.attempts_per_closed_product_goal == 2.0
    assert record.after_window.failure_reason_summary == '{"validation_failed": 1}'
    assert record.delta.delta_attempts_per_closed_product_goal == 0.5
    assert record.delta.delta_known_cost_per_success_usd == -1.5


def test_derive_retro_timeline_persists_sqlite_tables(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics" / "events.ndjson"
    warehouse_path = tmp_path / "metrics" / ".codex-metrics" / "retro.sqlite"
    _build_normalized_history_db(warehouse_path, tmp_path)

    report = derive_retro_timeline(
        _build_metrics_data(),
        warehouse_path=warehouse_path,
        cwd=tmp_path,
        metrics_path=metrics_path,
        window_size=2,
    )

    assert report.warehouse_path == warehouse_path
    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM retro_timeline_events").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM retro_metric_windows").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM retro_window_deltas").fetchone()[0] == 1

        event = conn.execute(
            "SELECT message_id, source_kind, retro_file_path, title FROM retro_timeline_events WHERE retro_event_id = ?",
            ("retro-event:2026-04-03-message-level-retro",),
        ).fetchone()
        assert event["message_id"] == "msg-1"
        assert event["source_kind"] == "message"
        assert event["retro_file_path"] == "docs/retros/2026-04-03-message-level-retro.md"
        assert event["title"] == "message level retro"

        before_window = conn.execute(
            "SELECT product_goals_closed, exact_fit_rate, attempts_per_closed_product_goal FROM retro_metric_windows WHERE retro_event_id = ? AND window_side = ?",
            ("retro-event:2026-04-03-message-level-retro", "before"),
        ).fetchone()
        assert before_window["product_goals_closed"] == 2
        assert before_window["exact_fit_rate"] == 0.5
        assert before_window["attempts_per_closed_product_goal"] == 1.5

        delta = conn.execute(
            "SELECT delta_attempts_per_closed_product_goal, delta_known_cost_per_success_usd FROM retro_window_deltas WHERE retro_event_id = ?",
            ("retro-event:2026-04-03-message-level-retro",),
        ).fetchone()
        assert delta["delta_attempts_per_closed_product_goal"] == 0.5
        assert delta["delta_known_cost_per_success_usd"] == -1.5


def test_derive_retro_timeline_command_writes_report_and_tables(repo: Path) -> None:
    metrics_path = repo / "metrics" / "events.ndjson"
    warehouse_path = repo / "metrics" / ".codex-metrics" / "retro.sqlite"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    # Write goals as NDJSON events (one event per goal)
    metrics_data = _build_metrics_data()
    with metrics_path.open("w", encoding="utf-8") as f:
        for goal in metrics_data["goals"]:
            goal_with_all_fields = {
                "agent_name": None,
                **goal,
            }
            event = {"event_type": "goal_started", "ts": goal["started_at"], "goal": goal_with_all_fields, "entries": []}
            f.write(json.dumps(event) + "\n")
    _build_normalized_history_db(warehouse_path, repo)

    result = run_cmd(
        repo,
        "derive-retro-timeline",
        "--metrics-path",
        str(metrics_path),
        "--warehouse-path",
        str(warehouse_path),
        "--window-size",
        "2",
    )

    assert result.returncode == 0, result.stderr
    assert "Retrospective Timeline Report" in result.stdout
    assert "Retro events: 1" in result.stdout
    assert "delta_attempts_per_goal: 0.5" in result.stdout
    assert "message_id: msg-1" in result.stdout
    assert "source_kind: message" in result.stdout
    assert "retro_file_path: docs/retros/2026-04-03-message-level-retro.md" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM retro_timeline_events").fetchone()[0] == 1
