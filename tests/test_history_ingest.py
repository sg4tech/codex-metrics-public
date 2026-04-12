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

from ai_agents_metrics.history_ingest import (
    _encode_claude_cwd,
    _extract_claude_token_usage,
    _extract_message_text,
    _import_claude_session_file,
    _optional_row_value,
)


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
ABS_SCRIPT = _SCRIPTS_DIR / "metrics_cli.py"
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

    script_target = tmp_path / "scripts" / "metrics_cli.py"
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    first = run_cmd(
        repo,
        "history-ingest",
        "--source-root",
        str(source_root),
        "--warehouse-path",
        str(warehouse_path),
    )
    second = run_cmd(
        repo,
        "history-ingest",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"
    missing_root = repo / "does-not-exist"

    result = run_cmd(
        repo,
        "history-ingest",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
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


# ---------------------------------------------------------------------------
# Claude Code adapter helpers
# ---------------------------------------------------------------------------

def _make_claude_session_jsonl(
    *,
    session_id: str,
    cwd: str,
    version: str = "2.1.0",
    messages: list[dict] | None = None,
) -> str:
    """Build a minimal Claude Code session JSONL string for tests."""
    lines: list[str] = []
    user_uuid = "uuid-user-1"
    assistant_uuid = "uuid-asst-1"

    lines.append(json.dumps({
        "type": "user",
        "uuid": user_uuid,
        "parentUuid": None,
        "sessionId": session_id,
        "timestamp": "2026-04-01T10:00:00.000Z",
        "cwd": cwd,
        "version": version,
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "hello from test"}],
        },
    }))
    if messages is None:
        messages = [
            {
                "type": "assistant",
                "uuid": assistant_uuid,
                "parentUuid": user_uuid,
                "sessionId": session_id,
                "timestamp": "2026-04-01T10:00:01.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-6",
                    "content": [{"type": "text", "text": "hi there"}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 200,
                        "cache_creation_input_tokens": 10,
                    },
                },
            }
        ]
    for msg in messages:
        lines.append(json.dumps(msg))
    return "\n".join(lines) + "\n"


def create_claude_history_source_root(
    root: Path,
    *,
    cwd: str | None = None,
    with_subagent: bool = False,
) -> Path:
    """Create a minimal ~/.claude layout for testing."""
    claude_root = root / "claude-source"
    project_cwd = cwd or str(root / "myproject")
    encoded = project_cwd.replace("/", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)

    session_id = "aaaa0000-0000-0000-0000-000000000001"
    (project_dir / f"{session_id}.jsonl").write_text(
        _make_claude_session_jsonl(session_id=session_id, cwd=project_cwd),
        encoding="utf-8",
    )
    if with_subagent:
        subagent_dir = project_dir / session_id / "subagents"
        subagent_dir.mkdir(parents=True)
        (subagent_dir / "agent-acompact-abc123.jsonl").write_text(
            _make_claude_session_jsonl(session_id=session_id, cwd=project_cwd),
            encoding="utf-8",
        )
    return claude_root


def test_encode_claude_cwd() -> None:
    assert _encode_claude_cwd("/Users/viktor/myproject") == "-Users-viktor-myproject"
    assert _encode_claude_cwd("/a/b/c") == "-a-b-c"
    assert _encode_claude_cwd("relative") == "relative"


def test_extract_claude_token_usage_happy_path() -> None:
    event = {
        "type": "assistant",
        "timestamp": "2026-04-01T10:00:01.000Z",
        "message": {
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 200,
                "cache_creation_input_tokens": 10,
            },
        },
    }
    result = _extract_claude_token_usage(
        event, event_id="eid-1", source_path="test.jsonl", thread_id="thread-1", event_index=0
    )
    assert result is not None
    assert result["input_tokens"] == 100
    assert result["cache_creation_input_tokens"] == 10
    assert result["cached_input_tokens"] == 200  # cache_read maps here
    assert result["output_tokens"] == 50
    assert result["total_tokens"] == 360  # 100 + 10 + 200 + 50
    assert result["model"] == "claude-sonnet-4-6"
    assert result["has_breakdown"] == 1


def test_extract_claude_token_usage_non_assistant_returns_none() -> None:
    event = {"type": "user", "message": {"usage": {"input_tokens": 10}}}
    assert _extract_claude_token_usage(
        event, event_id="e", source_path="f", thread_id="t", event_index=0
    ) is None


def test_extract_claude_token_usage_zero_total_returns_none() -> None:
    event = {
        "type": "assistant",
        "message": {"usage": {"input_tokens": 0, "output_tokens": 0}},
    }
    assert _extract_claude_token_usage(
        event, event_id="e", source_path="f", thread_id="t", event_index=0
    ) is None


def test_import_claude_session_file_populates_warehouse(tmp_path: Path) -> None:
    import sqlite3 as _sqlite3

    from ai_agents_metrics.history_ingest import _ensure_schema

    warehouse = tmp_path / "warehouse.sqlite"
    session_id = "bbbb0000-0000-0000-0000-000000000001"
    cwd = str(tmp_path / "proj")
    session_file = tmp_path / f"{session_id}.jsonl"
    session_file.write_text(
        _make_claude_session_jsonl(session_id=session_id, cwd=cwd),
        encoding="utf-8",
    )

    with _sqlite3.connect(warehouse) as conn:
        conn.row_factory = _sqlite3.Row
        _ensure_schema(conn)
        _import_claude_session_file(conn, session_file)

        thread = conn.execute(
            "SELECT thread_id, model_provider, cwd FROM raw_threads WHERE thread_id = ?",
            (session_id,),
        ).fetchone()
        assert thread is not None
        assert thread["model_provider"] == "anthropic"
        assert thread["cwd"] == cwd

        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 2  # user + assistant
        usage = conn.execute("SELECT * FROM raw_token_usage").fetchone()
        assert usage is not None
        assert usage["input_tokens"] == 100
        assert usage["cache_creation_input_tokens"] == 10
        assert usage["cached_input_tokens"] == 200
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 360


def test_import_claude_subagent_groups_under_same_thread(tmp_path: Path) -> None:
    import sqlite3 as _sqlite3

    from ai_agents_metrics.history_ingest import _ensure_schema

    warehouse = tmp_path / "warehouse.sqlite"
    session_id = "cccc0000-0000-0000-0000-000000000001"
    cwd = str(tmp_path / "proj")

    # Parent session
    parent_file = tmp_path / f"{session_id}.jsonl"
    parent_file.write_text(
        _make_claude_session_jsonl(session_id=session_id, cwd=cwd),
        encoding="utf-8",
    )
    # Subagent file shares the same sessionId
    subagent_dir = tmp_path / session_id / "subagents"
    subagent_dir.mkdir(parents=True)
    subagent_file = subagent_dir / "agent-acompact-abc123.jsonl"
    subagent_file.write_text(
        _make_claude_session_jsonl(session_id=session_id, cwd=cwd),
        encoding="utf-8",
    )

    with _sqlite3.connect(warehouse) as conn:
        conn.row_factory = _sqlite3.Row
        _ensure_schema(conn)
        _import_claude_session_file(conn, parent_file)
        _import_claude_session_file(conn, subagent_file)

        # Only one thread row (INSERT OR IGNORE on shared sessionId)
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 1
        # Two session rows (one per file)
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 2
        # Both sessions share the same thread_id
        thread_ids = [
            r[0]
            for r in conn.execute("SELECT DISTINCT thread_id FROM raw_sessions").fetchall()
        ]
        assert thread_ids == [session_id]


def test_ingest_claude_history_builds_raw_warehouse(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
        "--source",
        "claude",
        "--source-root",
        str(claude_root),
        "--warehouse-path",
        str(warehouse_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Ingested Codex history into" in result.stdout
    assert "Imported files: 1" in result.stdout
    assert "Threads: 1" in result.stdout
    assert "Sessions: 1" in result.stdout
    assert "Messages: 2" in result.stdout
    assert "Token usage events: 1" in result.stdout
    assert "Input tokens: 100" in result.stdout
    assert "Cached input tokens: 200" in result.stdout
    assert "Output tokens: 50" in result.stdout
    assert "Total tokens: 360" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM raw_token_usage").fetchone()[0] == 1

        thread = conn.execute("SELECT * FROM raw_threads").fetchone()
        assert thread["model_provider"] == "anthropic"

        usage = conn.execute("SELECT * FROM raw_token_usage").fetchone()
        assert usage["input_tokens"] == 100
        assert usage["cache_creation_input_tokens"] == 10
        assert usage["cached_input_tokens"] == 200
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 360


def test_ingest_claude_history_subagent_groups_under_same_thread_cli(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-ingest",
        "--source", "claude",
        "--source-root", str(claude_root),
        "--warehouse-path", str(warehouse_path),
    )

    assert result.returncode == 0, result.stderr
    assert "Imported files: 2" in result.stdout
    # Parent creates 1 thread; subagent shares sessionId → INSERT OR IGNORE → still 1 thread
    assert "Threads: 1" in result.stdout
    assert "Sessions: 2" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 2


def test_ingest_claude_history_is_idempotent_on_rerun(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    first = run_cmd(
        repo,
        "history-ingest",
        "--source", "claude",
        "--source-root", str(claude_root),
        "--warehouse-path", str(warehouse_path),
    )
    second = run_cmd(
        repo,
        "history-ingest",
        "--source", "claude",
        "--source-root", str(claude_root),
        "--warehouse-path", str(warehouse_path),
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "Skipped files: 1" in second.stdout

    with sqlite3.connect(warehouse_path) as conn:
        assert conn.execute("SELECT count(*) FROM raw_threads").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_sessions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM raw_messages").fetchone()[0] == 2
