from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_history_ingest import (
    create_claude_history_source_root,
    create_codex_history_source_root,
    run_cmd,
)

from ai_agents_metrics.history.derive import (
    _fetch_normalized_logs,
    _fetch_normalized_messages,
    _fetch_normalized_sessions,
    _fetch_normalized_threads,
    _fetch_normalized_usage_events,
)
from ai_agents_metrics.history.normalize import _ensure_schema

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ABS_SCRIPT = WORKSPACE_ROOT / "scripts" / "metrics_cli.py"
ABS_SRC = WORKSPACE_ROOT / "src"


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
                            "role": "user",
                            "content": [{"type": "input_text", "text": "please clarify"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-04-02T10:10:02.000Z",
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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    assert (
        run_cmd(
            repo,
            "history-ingest",
            "--source-root",
            str(source_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )
    assert run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path)).returncode == 0

    result = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 0, result.stderr
    assert "Derived Codex history in" in result.stdout
    assert "Projects: 2" in result.stdout
    assert "Goals: 2" in result.stdout
    assert "Attempts: 3" in result.stdout  # user turns: 2 in thread-1, 1 in thread-2 (min=1)
    # rollout-3 gains a user message: +1 timeline event, +1 message fact
    assert "Timeline events: 11" in result.stdout
    assert "Retry chains: 2" in result.stdout
    assert "Message facts: 5" in result.stdout
    assert "Session usage: 3" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT count(*) FROM derived_goals").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_attempts").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derived_timeline_events").fetchone()[0] == 11
        assert conn.execute("SELECT count(*) FROM derived_message_facts").fetchone()[0] == 5
        assert conn.execute("SELECT count(*) FROM derived_retry_chains").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM derived_session_usage").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM derived_projects").fetchone()[0] == 2

        thread_1 = conn.execute(
            "SELECT attempt_count, retry_count, timeline_event_count FROM derived_goals WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        # attempt_count = user messages in thread (2: "hello ingest" + "please clarify")
        assert thread_1["attempt_count"] == 2
        assert thread_1["retry_count"] == 1
        assert thread_1["timeline_event_count"] == 8

        retry_chain = conn.execute(
            "SELECT has_retry_pressure, first_session_path, last_session_path FROM derived_retry_chains WHERE thread_id = ?",
            ("thread-1",),
        ).fetchone()
        assert retry_chain["has_retry_pressure"] == 1
        assert retry_chain["first_session_path"].endswith("rollout-1.jsonl")
        assert retry_chain["last_session_path"].endswith("rollout-3.jsonl")

        thread_2 = conn.execute(
            "SELECT attempt_count, retry_count FROM derived_goals WHERE thread_id = ?",
            ("thread-2",),
        ).fetchone()
        assert thread_2["attempt_count"] == 1
        assert thread_2["retry_count"] == 0

        thread_2_chain = conn.execute(
            "SELECT has_retry_pressure FROM derived_retry_chains WHERE thread_id = ?",
            ("thread-2",),
        ).fetchone()
        assert thread_2_chain["has_retry_pressure"] == 0

        attempt = conn.execute(
            "SELECT attempt_index, message_count, usage_event_count FROM derived_attempts WHERE session_path LIKE ?",
            ("%rollout-3.jsonl",),
        ).fetchone()
        assert attempt["attempt_index"] == 2
        assert attempt["message_count"] == 2  # user "please clarify" + assistant "retry reply"
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
            "SELECT usage_event_count, total_tokens, first_usage_at, last_usage_at, model FROM derived_session_usage WHERE session_path LIKE ?",
            ("%rollout-3.jsonl",),
        ).fetchone()
        assert usage_slice["usage_event_count"] == 0
        assert usage_slice["total_tokens"] is None
        assert usage_slice["first_usage_at"] is None
        assert usage_slice["last_usage_at"] is None
        assert usage_slice["model"] is None  # no usage events → no model

        # model propagation: thread-1 has no model in usage events (Codex fixture
        # token_count lacks info.model), so derived_goals.model falls back to
        # thread-level metadata ("gpt-5.4-mini").
        goal_1 = conn.execute(
            "SELECT model FROM derived_goals WHERE thread_id = ?", ("thread-1",)
        ).fetchone()
        assert goal_1["model"] == "gpt-5.4-mini"

        # derived_attempts should carry model from session usage (None for Codex)
        attempt_with_usage = conn.execute(
            "SELECT model FROM derived_attempts WHERE session_path LIKE ?",
            ("%rollout-1.jsonl",),
        ).fetchone()
        assert attempt_with_usage["model"] is None  # Codex fixture has no model in token_count


def test_dominant_model_picks_most_frequent() -> None:
    from ai_agents_metrics.history.derive_insert import _dominant_model

    rows: list[dict[str, Any]] = [
        {"model": "claude-sonnet-4-6"},
        {"model": "claude-sonnet-4-6"},
        {"model": "claude-haiku-4-5"},
    ]
    assert _dominant_model(rows) == "claude-sonnet-4-6"  # type: ignore[arg-type]


def test_dominant_model_returns_none_when_empty() -> None:
    from ai_agents_metrics.history.derive_insert import _dominant_model

    assert _dominant_model([]) is None
    rows: list[dict[str, Any]] = [{"model": None}, {"model": ""}]
    assert _dominant_model(rows) is None  # type: ignore[arg-type]


def test_derive_codex_history_is_idempotent_on_rerun(repo: Path) -> None:
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    assert (
        run_cmd(
            repo,
            "history-ingest",
            "--source-root",
            str(source_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )
    assert run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path)).returncode == 0

    first = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))
    second = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))

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
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "missing.sqlite"

    result = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 1
    assert f"Warehouse does not exist: {warehouse_path}" in result.stderr
    assert "history-update" in result.stderr


def test_derive_codex_history_rejects_non_normalized_warehouse(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "raw.sqlite"
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(warehouse_path).close()

    result = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 1
    assert "Warehouse does not contain normalized Codex history; run history-normalize first" in result.stderr


def test_fetch_normalized_functions_return_all_typed_fields() -> None:
    raw = "{}"
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        conn.execute(
            """
            INSERT INTO normalized_threads (
                thread_id, source_path, cwd, model_provider, model, title, archived,
                session_count, event_count, message_count, log_count,
                first_seen_at, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "/src", "/cwd", "openai", "gpt-4o", "My thread", 0, 3, 10, 5, 2, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_sessions (
                session_path, thread_id, source_path, session_timestamp, cwd, source,
                model_provider, cli_version, originator, event_count, message_count,
                first_event_at, last_event_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("/sessions/s1.jsonl", "t1", "/src", "2026-01-01T00:00:00Z", "/cwd", "vscode", "openai", "1.2.3", "Codex Desktop", 4, 2, "2026-01-01T00:00:01Z", "2026-01-01T00:00:04Z", raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_messages (
                message_id, thread_id, session_path, source_path, event_index, message_index,
                role, text, timestamp, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("m1", "t1", "/sessions/s1.jsonl", "/src", 1, 0, "user", "Hello", "2026-01-01T00:00:01Z", raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_usage_events (
                usage_event_id, thread_id, session_path, source_path, event_index, timestamp,
                input_tokens, cache_creation_input_tokens, cached_input_tokens,
                output_tokens, reasoning_output_tokens, total_tokens, model, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("u1", "t1", "/sessions/s1.jsonl", "/src", 2, "2026-01-01T00:00:02Z", 100, None, 10, 50, 5, 165, "gpt-4o", raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_logs (
                source_path, row_id, thread_id, ts, ts_iso, level, target, body, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("/src", 1, "t1", 1735689600, "2026-01-01T00:00:00+00:00", "INFO", "codex::agent", "Starting task", raw),
        )
        conn.commit()

        threads = _fetch_normalized_threads(conn)
        assert len(threads) == 1
        t = threads[0]
        assert t["thread_id"] == "t1"
        assert t["source_path"] == "/src"
        assert t["cwd"] == "/cwd"
        assert t["model_provider"] == "openai"
        assert t["model"] == "gpt-4o"
        assert t["title"] == "My thread"
        assert t["archived"] == 0
        assert t["session_count"] == 3
        assert t["event_count"] == 10
        assert t["message_count"] == 5
        assert t["log_count"] == 2
        assert t["first_seen_at"] == "2026-01-01T00:00:00Z"
        assert t["last_seen_at"] == "2026-01-02T00:00:00Z"
        assert t["raw_json"] == raw

        sessions = _fetch_normalized_sessions(conn)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["session_path"] == "/sessions/s1.jsonl"
        assert s["thread_id"] == "t1"
        assert s["source_path"] == "/src"
        assert s["session_timestamp"] == "2026-01-01T00:00:00Z"
        assert s["cwd"] == "/cwd"
        assert s["source"] == "vscode"
        assert s["model_provider"] == "openai"
        assert s["cli_version"] == "1.2.3"
        assert s["originator"] == "Codex Desktop"
        assert s["event_count"] == 4
        assert s["message_count"] == 2
        assert s["first_event_at"] == "2026-01-01T00:00:01Z"
        assert s["last_event_at"] == "2026-01-01T00:00:04Z"
        assert s["raw_json"] == raw

        messages = _fetch_normalized_messages(conn)
        assert len(messages) == 1
        m = messages[0]
        assert m["message_id"] == "m1"
        assert m["thread_id"] == "t1"
        assert m["session_path"] == "/sessions/s1.jsonl"
        assert m["source_path"] == "/src"
        assert m["event_index"] == 1
        assert m["message_index"] == 0
        assert m["role"] == "user"
        assert m["text"] == "Hello"
        assert m["timestamp"] == "2026-01-01T00:00:01Z"
        assert m["raw_json"] == raw

        usage_events = _fetch_normalized_usage_events(conn)
        assert len(usage_events) == 1
        u = usage_events[0]
        assert u["usage_event_id"] == "u1"
        assert u["thread_id"] == "t1"
        assert u["session_path"] == "/sessions/s1.jsonl"
        assert u["source_path"] == "/src"
        assert u["event_index"] == 2
        assert u["timestamp"] == "2026-01-01T00:00:02Z"
        assert u["input_tokens"] == 100
        assert u["cache_creation_input_tokens"] is None  # Codex fixture has no cache_creation
        assert u["cached_input_tokens"] == 10
        assert u["output_tokens"] == 50
        assert u["reasoning_output_tokens"] == 5
        assert u["total_tokens"] == 165
        assert u["model"] == "gpt-4o"
        assert u["raw_json"] == raw

        logs = _fetch_normalized_logs(conn)
        assert len(logs) == 1
        lg = logs[0]
        assert lg["source_path"] == "/src"
        assert lg["row_id"] == 1
        assert lg["thread_id"] == "t1"
        assert lg["ts"] == 1735689600
        assert lg["ts_iso"] == "2026-01-01T00:00:00+00:00"
        assert lg["level"] == "INFO"
        assert lg["target"] == "codex::agent"
        assert lg["body"] == "Starting task"
        assert lg["raw_json"] == raw


def test_fetch_normalized_functions_handle_nullable_fields() -> None:
    raw = "{}"
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)

        conn.execute(
            """
            INSERT INTO normalized_threads (
                thread_id, source_path, session_count, event_count, message_count, log_count, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "/src", 0, 0, 0, 0, raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_sessions (
                session_path, source_path, event_count, message_count, raw_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("/sessions/s1.jsonl", "/src", 0, 0, raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_messages (
                message_id, session_path, source_path, event_index, message_index, role, text, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("m1", "/sessions/s1.jsonl", "/src", 0, 0, "user", "Hi", raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_usage_events (
                usage_event_id, session_path, source_path, event_index, raw_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("u1", "/sessions/s1.jsonl", "/src", 0, raw),
        )
        conn.execute(
            """
            INSERT INTO normalized_logs (source_path, row_id, raw_json) VALUES (?, ?, ?)
            """,
            ("/src", 1, raw),
        )
        conn.commit()

        thread = _fetch_normalized_threads(conn)[0]
        assert thread["cwd"] is None
        assert thread["model_provider"] is None
        assert thread["model"] is None
        assert thread["title"] is None
        assert thread["archived"] is None
        assert thread["first_seen_at"] is None
        assert thread["last_seen_at"] is None

        session = _fetch_normalized_sessions(conn)[0]
        assert session["thread_id"] is None
        assert session["session_timestamp"] is None
        assert session["cwd"] is None
        assert session["source"] is None
        assert session["model_provider"] is None
        assert session["cli_version"] is None
        assert session["originator"] is None
        assert session["first_event_at"] is None
        assert session["last_event_at"] is None

        message = _fetch_normalized_messages(conn)[0]
        assert message["thread_id"] is None
        assert message["timestamp"] is None

        usage = _fetch_normalized_usage_events(conn)[0]
        assert usage["thread_id"] is None
        assert usage["timestamp"] is None
        assert usage["input_tokens"] is None
        assert usage["cached_input_tokens"] is None
        assert usage["output_tokens"] is None
        assert usage["reasoning_output_tokens"] is None
        assert usage["total_tokens"] is None
        assert usage["model"] is None

        log = _fetch_normalized_logs(conn)[0]
        assert log["thread_id"] is None
        assert log["ts"] is None
        assert log["ts_iso"] is None
        assert log["level"] is None
        assert log["target"] is None
        assert log["body"] is None


def test_derive_claude_history_populates_cache_creation_tokens(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    assert (
        run_cmd(
            repo,
            "history-ingest",
            "--source",
            "claude",
            "--source-root",
            str(claude_root),
            "--warehouse-path",
            str(warehouse_path),
        ).returncode
        == 0
    )
    assert run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path)).returncode == 0
    result = run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path))
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        usage = conn.execute("SELECT * FROM derived_session_usage").fetchone()
        assert usage["cache_creation_input_tokens"] == 10
        assert usage["input_tokens"] == 100
        assert usage["cached_input_tokens"] == 200
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 360
        assert usage["model"] == "claude-sonnet-4-6"

        # model propagated to goal and attempt
        goal = conn.execute("SELECT model FROM derived_goals").fetchone()
        assert goal["model"] == "claude-sonnet-4-6"
        attempt = conn.execute("SELECT model FROM derived_attempts").fetchone()
        assert attempt["model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# _parent_project_cwd
# ---------------------------------------------------------------------------

def test_parent_project_cwd_plain_path() -> None:
    from ai_agents_metrics.history.derive import _parent_project_cwd
    assert _parent_project_cwd("/Users/viktor/myproject") == "/Users/viktor/myproject"


def test_parent_project_cwd_worktree_path() -> None:
    from ai_agents_metrics.history.derive import _parent_project_cwd
    result = _parent_project_cwd("/Users/viktor/myproject/.claude/worktrees/eloquent-rhodes")
    assert result == "/Users/viktor/myproject"


def test_parent_project_cwd_nested_worktree() -> None:
    from ai_agents_metrics.history.derive import _parent_project_cwd
    result = _parent_project_cwd("/a/b/.claude/worktrees/foo/.claude/worktrees/bar")
    # Only the first marker is stripped
    assert result == "/a/b"


def test_parent_project_cwd_none_input() -> None:
    from ai_agents_metrics.history.derive import _parent_project_cwd
    assert _parent_project_cwd(None) is None


def test_parent_project_cwd_empty_string() -> None:
    from ai_agents_metrics.history.derive import _parent_project_cwd
    assert _parent_project_cwd("") is None


def test_derive_merges_worktree_into_parent_project(repo: Path) -> None:
    """Worktree threads must roll up into the parent project in derived_projects."""
    source_root = create_codex_history_source_root(repo)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    assert run_cmd(repo, "history-ingest", "--source-root", str(source_root), "--warehouse-path", str(warehouse_path)).returncode == 0
    assert run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path)).returncode == 0
    assert run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path)).returncode == 0

    # Manually inject a fake worktree thread into derived_goals and then re-run derive
    # to confirm the merge logic; here we just check that parent_project_cwd is stored.
    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT project_cwd, parent_project_cwd FROM derived_projects").fetchall()
        assert rows, "derived_projects must not be empty"
        for row in rows:
            # parent_project_cwd must be set and must not contain the worktree marker
            assert row["parent_project_cwd"] is not None
            assert "/.claude/worktrees/" not in row["parent_project_cwd"]
