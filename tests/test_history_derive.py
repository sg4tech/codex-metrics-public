from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.test_history_ingest import create_codex_history_source_root, run_cmd

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


def _add_retry_session(source_root: Path) -> None:
    sessions_dir = source_root / "sessions" / "2026" / "04" / "02"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    retry_session = sessions_dir / "rollout-3.jsonl"
    retry_session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:10:00.000Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "thread-1",
                            "timestamp": "2026-04-02T10:10:00.000Z",
                            "cwd": str(source_root),
                            "originator": "Codex Desktop",
                            "cli_version": "0.118.0",
                            "source": "vscode",
                            "model_provider": "openai",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:10:01.000Z",
                        "type": "response_item",
                        "payload": {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "retry reply"}],
                        },
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_derive_codex_history_builds_analysis_marts(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    _add_retry_session(source_root)
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
    assert run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path)).returncode == 0

    result = run_cmd(repo, "derive-codex-history", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 0, result.stderr
    assert "Derived Codex history in" in result.stdout
    assert "Projects: 2" in result.stdout
    assert "Goals: 2" in result.stdout
    assert "Attempts: 3" in result.stdout
    assert "Timeline events: 10" in result.stdout
    assert "Retry chains: 2" in result.stdout
    assert "Message facts: 4" in result.stdout
    assert "Session usage: 3" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM derived_goals").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_attempts").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derived_timeline_events").fetchone()[0] == 10
        assert conn.execute("SELECT count(*) FROM derived_message_facts").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM derived_retry_chains").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_session_usage").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derived_projects").fetchone()[0] == 2

        thread_1 = conn.execute(
            "SELECT attempt_count, retry_count, timeline_event_count FROM derived_goals WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        assert thread_1["attempt_count"] == 2
        assert thread_1["retry_count"] == 1
        assert thread_1["timeline_event_count"] == 7

        retry_chain = conn.execute(
            "SELECT has_retry_pressure, first_attempt_session_path, last_attempt_session_path FROM derived_retry_chains WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        assert retry_chain["has_retry_pressure"] == 1
        assert retry_chain["first_attempt_session_path"].endswith("rollout-1.jsonl")
        assert retry_chain["last_attempt_session_path"].endswith("rollout-3.jsonl")

        attempt = conn.execute(
            "SELECT attempt_index, message_count, usage_event_count FROM derived_attempts WHERE session_path LIKE ?",
            ("%rollout-3.jsonl",),
        ).fetchone()
        assert attempt["attempt_index"] == 2
        assert attempt["message_count"] == 1
        assert attempt["usage_event_count"] == 0

        user_message = conn.execute(
            "SELECT message_date, model, total_tokens FROM derived_message_facts WHERE role = 'user' AND text = ?",
            ("hello ingest",),
        ).fetchone()
        assert user_message["message_date"] == "2026-04-02"
        assert user_message["model"] == "gpt-5.4-mini"
        assert user_message["total_tokens"] is None

        assistant_message = conn.execute(
            "SELECT message_date, model, total_tokens, input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens FROM derived_message_facts WHERE role = 'assistant' AND text = ?",
            ("hi there",),
        ).fetchone()
        assert assistant_message["message_date"] == "2026-04-02"
        assert assistant_message["model"] == "gpt-5.4-mini"
        assert assistant_message["input_tokens"] == 100
        assert assistant_message["cached_input_tokens"] == 10
        assert assistant_message["output_tokens"] == 50
        assert assistant_message["reasoning_output_tokens"] == 5
        assert assistant_message["total_tokens"] == 165

        usage_slice = conn.execute(
            "SELECT usage_event_count, total_tokens, first_usage_at, last_usage_at FROM derived_session_usage WHERE session_path LIKE ?",
            ("%rollout-3.jsonl",),
        ).fetchone()
        assert usage_slice["usage_event_count"] == 0
        assert usage_slice["total_tokens"] is None
        assert usage_slice["first_usage_at"] is None
        assert usage_slice["last_usage_at"] is None


def test_derive_codex_history_is_idempotent_on_rerun(repo: Path) -> None:
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
    assert run_cmd(repo, "normalize-codex-history", "--warehouse-path", str(warehouse_path)).returncode == 0

    first = run_cmd(repo, "derive-codex-history", "--warehouse-path", str(warehouse_path))
    second = run_cmd(repo, "derive-codex-history", "--warehouse-path", str(warehouse_path))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Projects: 2" in second.stdout
    assert "Goals: 2" in second.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM derived_goals").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_attempts").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_timeline_events").fetchone()[0] == 8
        assert conn.execute("SELECT count(*) FROM derived_message_facts").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derived_retry_chains").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_session_usage").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_projects").fetchone()[0] == 2


def test_derive_codex_history_rejects_missing_normalized_warehouse(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".codex-metrics" / "missing.sqlite"

    result = run_cmd(repo, "derive-codex-history", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 1
    assert f"Warehouse does not exist: {warehouse_path}" in result.stderr


def test_derive_codex_history_rejects_non_normalized_warehouse(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".codex-metrics" / "raw.sqlite"
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(warehouse_path).close()

    result = run_cmd(repo, "derive-codex-history", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 1
    assert "Warehouse does not contain normalized Codex history; run normalize-codex-history first" in result.stderr
