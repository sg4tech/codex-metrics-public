from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from test_history_ingest import (
    create_claude_history_source_root,
    run_cmd,
)

from ai_agents_metrics.history.classify import (
    CLASSIFIER_VERSION,
    SESSION_KIND_MAIN,
    SESSION_KIND_SUBAGENT,
    SESSION_KIND_UNKNOWN,
    _classify_session_kind,
    classify_codex_history,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
ABS_SCRIPT = WORKSPACE_ROOT / "scripts" / "metrics_cli.py"
ABS_SRC = WORKSPACE_ROOT / "src"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "metrics").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pricing").mkdir(parents=True, exist_ok=True)

    if os.environ.get("CODEX_SUBPROCESS_COVERAGE") == "1":
        (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
        script_target = tmp_path / "scripts" / "metrics_cli.py"
        script_target.write_text(ABS_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        shutil.copytree(ABS_SRC, tmp_path / "src")

    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=tmp_path, text=True, capture_output=True, check=True)
    return tmp_path


# Unit tests for the pure filename classifier — these lock the F-001 deterministic rule.


def test_classify_claude_main_session() -> None:
    path = "/home/u/.claude/projects/-a-b/aaaa0000-0000-0000-0000-000000000001.jsonl"
    assert _classify_session_kind(path) == SESSION_KIND_MAIN


def test_classify_claude_subagent_by_agent_prefix() -> None:
    path = "/home/u/.claude/projects/-a-b/thread/subagents/agent-abc123.jsonl"
    assert _classify_session_kind(path) == SESSION_KIND_SUBAGENT


def test_classify_claude_compact_subagent() -> None:
    path = "/home/u/.claude/projects/-a-b/thread/subagents/agent-acompact-xyz.jsonl"
    assert _classify_session_kind(path) == SESSION_KIND_SUBAGENT


def test_classify_codex_rollout_is_main() -> None:
    path = "/home/u/.codex/sessions/2026/04/02/rollout-2026-04-02T10-00-00-thread1.jsonl"
    assert _classify_session_kind(path) == SESSION_KIND_MAIN


def test_classify_empty_returns_unknown() -> None:
    assert _classify_session_kind("") == SESSION_KIND_UNKNOWN


def test_classify_non_jsonl_returns_unknown() -> None:
    assert _classify_session_kind("/tmp/notes.txt") == SESSION_KIND_UNKNOWN


def test_classify_windows_style_subagent_path() -> None:
    # Python os.path.basename keeps the full string when path uses backslashes on POSIX,
    # but the '/subagents/' substring check relies on the normalized forward-slash form.
    path = "C:\\history\\.claude\\projects\\abc\\thread\\subagents\\agent-abc.jsonl"
    # basename starts with 'agent-' after normalization of backslashes into a stem
    # that ends in 'agent-abc.jsonl'. We rely on os.path.basename's POSIX behavior
    # which treats backslashes as part of the name, so the substring check kicks in.
    assert _classify_session_kind(path) == SESSION_KIND_SUBAGENT


def test_classifier_version_is_stable() -> None:
    # Guardrail: the version is deterministic across runs so classifier output is
    # idempotent unless rules change.
    assert CLASSIFIER_VERSION.startswith("v1-")
    assert len(CLASSIFIER_VERSION) == len("v1-") + 8


# End-to-end: ingest + normalize + classify populates derived_session_kinds.


def test_classify_codex_history_populates_session_kinds(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
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

    summary = classify_codex_history(warehouse_path=warehouse_path)

    assert summary.sessions_total == 2
    assert summary.main_sessions == 1
    assert summary.subagent_sessions == 1
    assert summary.unknown_sessions == 0
    assert summary.classifier_version == CLASSIFIER_VERSION

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        kinds = {row["session_path"]: row["kind"] for row in conn.execute(
            "SELECT session_path, kind FROM derived_session_kinds"
        ).fetchall()}
    # Main file is <uuid>.jsonl, subagent is agent-acompact-*.jsonl.
    main_paths = [p for p in kinds if not Path(p).name.startswith("agent-")]
    subagent_paths = [p for p in kinds if Path(p).name.startswith("agent-")]
    assert len(main_paths) == 1 and kinds[main_paths[0]] == SESSION_KIND_MAIN
    assert len(subagent_paths) == 1 and kinds[subagent_paths[0]] == SESSION_KIND_SUBAGENT


def test_classify_is_idempotent(repo: Path) -> None:
    """Running classify twice should yield the same row count, not duplicates."""
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    run_cmd(repo, "history-ingest", "--source", "claude", "--source-root",
            str(claude_root), "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path))

    classify_codex_history(warehouse_path=warehouse_path)
    classify_codex_history(warehouse_path=warehouse_path)

    with sqlite3.connect(warehouse_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM derived_session_kinds").fetchone()[0]
    assert count == 2


def test_classify_cli_command_runs(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    run_cmd(repo, "history-ingest", "--source", "claude", "--source-root",
            str(claude_root), "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path))

    result = run_cmd(repo, "history-classify", "--warehouse-path", str(warehouse_path))
    assert result.returncode == 0, result.stderr
    assert "Classifier version:" in result.stdout
    assert "Main sessions: 1" in result.stdout
    assert "Subagent sessions: 1" in result.stdout


def test_derive_populates_main_attempt_count_from_classified_kinds(repo: Path) -> None:
    """H-040 outcome: derive writes main_attempt_count reflecting classified 'main' sessions."""
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    run_cmd(repo, "history-ingest", "--source", "claude", "--source-root",
            str(claude_root), "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-classify", "--warehouse-path", str(warehouse_path))
    assert run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path)).returncode == 0

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT session_count, main_attempt_count FROM derived_goals").fetchone()
    # Parent + subagent share the same thread_id -> session_count == 2, main_attempt_count == 1.
    # Before H-040 the naive retry metric treated this as an attempt=2 / retry=1 situation.
    assert row["session_count"] == 2
    assert row["main_attempt_count"] == 1


def test_derive_without_classify_sets_main_attempt_count_null(repo: Path) -> None:
    """Backward-compat: running derive on an unclassified warehouse yields NULL, not 0."""
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    run_cmd(repo, "history-ingest", "--source", "claude", "--source-root",
            str(claude_root), "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path))
    assert run_cmd(repo, "history-derive", "--warehouse-path", str(warehouse_path)).returncode == 0

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT main_attempt_count FROM derived_goals").fetchone()
    assert row["main_attempt_count"] is None


def test_classify_requires_normalized_history(repo: Path) -> None:
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"
    # Create empty warehouse without any tables.
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(warehouse_path).close()

    with pytest.raises(ValueError, match="normalized"):
        classify_codex_history(warehouse_path=warehouse_path)


def test_history_update_runs_classify_between_normalize_and_derive(repo: Path) -> None:
    claude_root = create_claude_history_source_root(repo, with_subagent=True)
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    result = run_cmd(
        repo,
        "history-update",
        "--source",
        "claude",
        "--source-root",
        str(claude_root),
        "--warehouse-path",
        str(warehouse_path),
    )
    assert result.returncode == 0, result.stderr
    assert "history-classify" in result.stdout
    assert "1 main, 1 subagent" in result.stdout

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT main_attempt_count FROM derived_goals").fetchone()
    assert row["main_attempt_count"] == 1
