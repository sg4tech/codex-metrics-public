from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from test_history_ingest import create_codex_history_source_root, run_cmd

from codex_metrics.history_normalize import _iso_from_unix_seconds, _usage_event_from_row

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ABS_SCRIPT = WORKSPACE_ROOT / "scripts" / "update_codex_metrics.py"
ABS_SRC = WORKSPACE_ROOT / "src"


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


def test_normalize_codex_history_builds_analysis_tables(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    ingest_result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )
    assert ingest_result.returncode == 0, ingest_result.stderr

    normalize_result = run_cmd(
        repo,
        "normalize-codex-history",
        "--warehouse-path",
        str(warehouse_path),
    )

    assert normalize_result.returncode == 0, normalize_result.stderr
    assert "Normalized Codex history in" in normalize_result.stdout
    assert "Projects: 2" in normalize_result.stdout
    assert "Threads: 2" in normalize_result.stdout
    assert "Sessions: 2" in normalize_result.stdout
    assert "Messages: 3" in normalize_result.stdout
    assert "Usage events: 1" in normalize_result.stdout
    assert "Logs: 2" in normalize_result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM normalized_threads").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_messages").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM normalized_usage_events").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM normalized_logs").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_projects").fetchone()[0] == 2

        session = conn.execute(
            "SELECT event_count, message_count, first_event_at, last_event_at FROM normalized_sessions WHERE session_path LIKE ?",
            ("%rollout-1.jsonl",),
        ).fetchone()
        assert session["event_count"] == 4
        assert session["message_count"] == 2
        assert session["first_event_at"] == "2026-04-02T10:00:00.000Z"
        assert session["last_event_at"] == "2026-04-02T10:00:03.000Z"

        usage = conn.execute(
            "SELECT input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens FROM normalized_usage_events WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        assert usage["input_tokens"] == 100
        assert usage["cached_input_tokens"] == 10
        assert usage["output_tokens"] == 50
        assert usage["reasoning_output_tokens"] == 5
        assert usage["total_tokens"] == 165


def test_normalize_codex_history_is_idempotent_on_rerun(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    assert (
        run_cmd(
            repo,
            "ingest-codex-history",
            "--source-root",
            str(source_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )

    first = run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path))
    second = run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Projects: 2" in second.stdout
    assert "Threads: 2" in second.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM normalized_threads").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_messages").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM normalized_usage_events").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM normalized_logs").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM normalized_projects").fetchone()[0] == 2


def test_normalize_codex_history_handles_missing_event_timestamps(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    assert (
        run_cmd(
            repo,
            "ingest-codex-history",
            "--source-root",
            str(source_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )

    with sqlite3.connect(warehouse_path) as conn:
        conn.execute(
            "UPDATE raw_session_events SET timestamp = NULL WHERE session_path LIKE ?",
            ("%rollout-2.jsonl",),
        )
        conn.commit()

    result = run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 0, result.stderr

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        session = conn.execute(
            "SELECT first_event_at, last_event_at FROM normalized_sessions WHERE session_path LIKE ?",
            ("%rollout-2.jsonl",),
        ).fetchone()
        assert session["first_event_at"] is None
        assert session["last_event_at"] is None
        message = conn.execute(
            "SELECT timestamp FROM normalized_messages WHERE session_path LIKE ? ORDER BY event_index LIMIT 1",
            ("%rollout-2.jsonl",),
        ).fetchone()
        assert message["timestamp"] is None


def test_normalize_codex_history_handles_blank_timestamp_strings(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    assert (
        run_cmd(
            repo,
            "ingest-codex-history",
            "--source-root",
            str(source_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )

    with sqlite3.connect(warehouse_path) as conn:
        conn.execute("UPDATE raw_sessions SET session_timestamp = '' WHERE session_path LIKE ?", ("%rollout-2.jsonl",))
        conn.execute("UPDATE raw_session_events SET timestamp = '' WHERE session_path LIKE ?", ("%rollout-2.jsonl",))
        conn.commit()

    result = run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 0, result.stderr

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        session = conn.execute(
            "SELECT first_event_at, last_event_at FROM normalized_sessions WHERE session_path LIKE ?",
            ("%rollout-2.jsonl",),
        ).fetchone()
        assert session["first_event_at"] is None
        assert session["last_event_at"] is None
        message = conn.execute(
            "SELECT timestamp FROM normalized_messages WHERE session_path LIKE ? ORDER BY event_index LIMIT 1",
            ("%rollout-2.jsonl",),
        ).fetchone()
        assert message["timestamp"] is None


def test_normalize_codex_history_rejects_missing_warehouse(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".codex-metrics" / "missing.sqlite"

    result = run_cmd(
        repo,
        "normalize-codex-history",
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 1
    assert f"Warehouse does not exist: {warehouse_path}" in result.stderr


def test_normalize_codex_history_rejects_non_ingested_warehouse(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".codex-metrics" / "empty.sqlite"
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(warehouse_path).close()

    result = run_cmd(
        repo,
        "normalize-codex-history",
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 1
    assert "Warehouse does not contain raw Codex history; run ingest-codex-history first" in result.stderr


def test_normalize_helpers_handle_missing_timestamps_and_malformed_usage_rows() -> None:
    assert _iso_from_unix_seconds(None) is None

    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE raw_session_events (
                event_id TEXT,
                session_path TEXT,
                source_path TEXT,
                thread_id TEXT,
                event_index INTEGER,
                event_type TEXT,
                timestamp TEXT,
                payload_type TEXT,
                role TEXT,
                raw_json TEXT
            )
            """
        )
        malformed_rows = [
            (
                "event-1",
                "session-1",
                "/tmp/source.jsonl",
                "thread-1",
                1,
                "event_msg",
                "2026-04-02T10:00:00.000Z",
                "token_count",
                None,
                '{"type":"event_msg","payload":{"type":"other"}}',
            ),
            (
                "event-2",
                "session-1",
                "/tmp/source.jsonl",
                "thread-1",
                2,
                "event_msg",
                "2026-04-02T10:00:01.000Z",
                "token_count",
                None,
                '{"type":"event_msg","payload":{"type":"token_count","info":"oops"}}',
            ),
            (
                "event-3",
                "session-1",
                "/tmp/source.jsonl",
                "thread-1",
                3,
                "event_msg",
                "2026-04-02T10:00:02.000Z",
                "token_count",
                None,
                '{"type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":"oops"}}}',
            ),
        ]
        conn.executemany("INSERT INTO raw_session_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", malformed_rows)
        rows = conn.execute("SELECT * FROM raw_session_events ORDER BY event_index").fetchall()

    assert _usage_event_from_row(rows[0]) is None
    assert _usage_event_from_row(rows[1]) is None
    assert _usage_event_from_row(rows[2]) is None
