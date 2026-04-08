from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from codex_metrics.history_ingest import _extract_message_text, _optional_row_value


def _find_paths() -> tuple[Path, Path, Path]:
    for parent in Path(__file__).resolve().parents:
        cfg = parent / "pyproject.toml"
        if not cfg.exists():
            continue
        with cfg.open("rb") as f:
            ct = tomllib.load(f).get("tool", {}).get("codex_tests")
        if ct:
            return parent, parent / ct["scripts"], parent / ct["src"]
    raise RuntimeError("No [tool.codex_tests] found in any pyproject.toml")


_REPO_ROOT, _SCRIPTS_DIR, _SRC_DIR = _find_paths()
ABS_SCRIPT = _SCRIPTS_DIR / "update_codex_metrics.py"
ABS_SRC = _SRC_DIR


def build_cmd(*args: str) -> list[str]:
    if os.environ.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        return [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--rcfile",
            str(_REPO_ROOT / "pyproject.toml"),
            "--parallel-mode",
            str(ABS_SCRIPT),
            *args,
        ]
    return [sys.executable, str(ABS_SCRIPT), *args]


def run_cmd(
    tmp_path: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        env["COVERAGE_FILE"] = str(_REPO_ROOT / ".coverage")
    if extra_env is not None:
        env.update(extra_env)
    cmd = build_cmd(*args)
    return subprocess.run(
        cmd,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


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


def create_codex_history_source_root(root: Path) -> Path:
    source_root = root / "codex-source"
    sessions_dir = source_root / "sessions" / "2026" / "04" / "02"
    archived_dir = source_root / "archived_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    archived_dir.mkdir(parents=True, exist_ok=True)

    state_path = source_root / "state_5.sqlite"
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
                id, rollout_path, created_at, updated_at, source, model_provider, cwd, title,
                archived, cli_version, first_user_message, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-1",
                str(sessions_dir / "rollout-1.jsonl"),
                100,
                200,
                "vscode",
                "openai",
                str(source_root),
                "Thread One",
                0,
                "0.118.0",
                "First message",
                "gpt-5.4-mini",
            ),
        )
        conn.execute(
            """
            INSERT INTO threads (
                id, rollout_path, created_at, updated_at, source, model_provider, cwd, title,
                archived, cli_version, first_user_message, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-2",
                str(archived_dir / "rollout-2.jsonl"),
                300,
                400,
                "vscode",
                "anthropic",
                str(source_root / "projects" / "thread-2"),
                "Thread Two",
                1,
                "0.118.0",
                "Second message",
                "claude-3-5-sonnet",
            ),
        )

    logs_path = source_root / "logs_1.sqlite"
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
            "INSERT INTO logs (ts, level, target, feedback_log_body, thread_id) VALUES (?, ?, ?, ?, ?)",
            (1, "INFO", "codex_core::stream_events_utils", "session event", "thread-1"),
        )
        conn.execute(
            "INSERT INTO logs (ts, level, target, feedback_log_body, thread_id) VALUES (?, ?, ?, ?, ?)",
            (2, "DEBUG", "codex_core::stream_events_utils", "more session event", "thread-2"),
        )

    rollout_1 = sessions_dir / "rollout-1.jsonl"
    rollout_1.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:00:00.000Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "thread-1",
                            "timestamp": "2026-04-02T10:00:00.000Z",
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
                        "timestamp": "2026-04-02T10:00:01.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "last_token_usage": {
                                    "input_tokens": 100,
                                    "cached_input_tokens": 10,
                                    "output_tokens": 50,
                                    "reasoning_output_tokens": 5,
                                    "total_tokens": 165,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:00:02.000Z",
                        "type": "response_item",
                        "payload": {
                            "role": "user",
                            "content": [{"type": "input_text", "text": "hello ingest"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:00:03.000Z",
                        "type": "response_item",
                        "payload": {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "hi there"}],
                        },
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    rollout_2 = archived_dir / "rollout-2.jsonl"
    rollout_2.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-04-02T11:00:00.000Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "thread-2",
                            "timestamp": "2026-04-02T11:00:00.000Z",
                            "cwd": str(source_root / "projects" / "thread-2"),
                            "originator": "Codex Desktop",
                            "cli_version": "0.118.0",
                            "source": "vscode",
                            "model_provider": "anthropic",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-02T11:00:01.000Z",
                        "type": "response_item",
                        "payload": {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "archived reply"}],
                        },
                    }
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    return source_root


def test_ingest_codex_history_builds_raw_warehouse(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Ingested Codex history into" in result.stdout
    assert "Imported files: 4" in result.stdout
    assert "Projects: 2" in result.stdout
    assert "Threads: 2" in result.stdout
    assert "Sessions: 2" in result.stdout
    assert "Session events: 6" in result.stdout
    assert "Token count events: 1" in result.stdout
    assert "Token usage events: 1" in result.stdout
    assert "Input tokens: 100" in result.stdout
    assert "Cached input tokens: 10" in result.stdout
    assert "Output tokens: 50" in result.stdout
    assert "Reasoning output tokens: 5" in result.stdout
    assert "Total tokens: 165" in result.stdout
    assert "Messages: 3" in result.stdout
    assert "Logs: 2" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM source_manifest").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 2
        assert conn.execute(
            """
            SELECT count(DISTINCT cwd)
            FROM (
                SELECT cwd FROM raw_threads WHERE cwd IS NOT NULL AND cwd != ''
                UNION ALL
                SELECT cwd FROM raw_sessions WHERE cwd IS NOT NULL AND cwd != ''
            )
            """
        ).fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_session_events").fetchone()[0] == 6
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM raw_token_usage").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_logs").fetchone()[0] == 2

        thread = conn.execute(
            "SELECT thread_id, model_provider, title, archived FROM raw_threads WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        assert thread["model_provider"] == "openai"
        assert thread["title"] == "Thread One"
        assert thread["archived"] == 0

        message = conn.execute(
            "SELECT role, text FROM raw_messages WHERE thread_id = ? ORDER BY event_index, message_index LIMIT 1",
            ("thread-1",),
        ).fetchone()
        assert message["role"] == "user"
        assert message["text"] == "hello ingest"


def test_ingest_codex_history_tracks_token_count_coverage(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    rollout_2 = source_root / "archived_sessions" / "rollout-2.jsonl"
    rollout_2.write_text(
        rollout_2.read_text(encoding="utf-8")
        + json.dumps(
            {
                "timestamp": "2026-04-02T11:00:02.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": None,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Session events: 7" in result.stdout
    assert "Token count events: 2" in result.stdout
    assert "Token usage events: 1" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM raw_token_usage").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_token_usage WHERE has_breakdown = 1").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_token_usage WHERE has_breakdown = 0").fetchone()[0] == 1


def test_ingest_codex_history_is_idempotent_on_rerun(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    first = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )
    second = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Skipped files: 4" in second.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM source_manifest").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_session_events").fetchone()[0] == 6
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM raw_logs").fetchone()[0] == 2


def test_ingest_codex_history_rejects_missing_source_root(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"
    missing_root = repo / "does-not-exist"

    result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(missing_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 1
    assert f"Source root does not exist: {missing_root}" in result.stderr


def test_ingest_codex_history_handles_partial_source_root_without_state_or_logs(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    (source_root / "state_5.sqlite").unlink()
    (source_root / "logs_1.sqlite").unlink()
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Imported files: 2" in result.stdout
    assert "Projects: 2" in result.stdout
    assert "Threads: 0" in result.stdout
    assert "Sessions: 2" in result.stdout
    assert "Session events: 6" in result.stdout
    assert "Messages: 3" in result.stdout
    assert "Logs: 0" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM source_manifest").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 2
        assert conn.execute(
            """
            SELECT count(DISTINCT cwd)
            FROM (
                SELECT cwd FROM raw_threads WHERE cwd IS NOT NULL AND cwd != ''
                UNION ALL
                SELECT cwd FROM raw_sessions WHERE cwd IS NOT NULL AND cwd != ''
            )
            """
        ).fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_session_events").fetchone()[0] == 6
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM raw_logs").fetchone()[0] == 0


def test_ingest_codex_history_rejects_malformed_sqlite_sources(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    with sqlite3.connect(source_root / "state_5.sqlite") as conn:
        conn.execute("DROP TABLE threads")
        conn.commit()
    warehouse_path = repo / "metrics" / ".codex-metrics" / "codex_raw_history.sqlite"

    result = run_cmd(
        repo,
        "ingest-codex-history",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 1
    assert "Source file is not a valid Codex thread state database" in result.stderr


def test_ingest_helpers_handle_sparse_rows_and_message_content() -> None:
    assert _optional_row_value({"present": "value"}, "present") == "value"
    assert _optional_row_value({"present": "value"}, "missing", "fallback") == "fallback"
    assert _extract_message_text("plain text message") == ["plain text message"]
    assert _extract_message_text(
        [
            "ignored string item",
            {"type": "input_text", "text": "hello"},
            {"type": "output_text", "text": ""},
            {"type": "text", "text": "world"},
            {"type": "other", "text": "skip me"},
        ]
    ) == ["hello", "world"]
