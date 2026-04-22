from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from conftest import find_repo_paths
from test_history_ingest import (
    create_claude_history_source_root,
    run_cmd,
)

from ai_agents_metrics.history.classify import (
    CLASSIFIER_VERSION,
    PRACTICE_EVENT_CLASSIFIER_VERSION,
    PRACTICE_FAMILY_CODE_REVIEW,
    PRACTICE_FAMILY_COMMIT_WORKFLOW,
    PRACTICE_FAMILY_DISCOVERY,
    PRACTICE_FAMILY_OTHER,
    PRACTICE_FAMILY_PLANNING,
    PRACTICE_SOURCE_AGENT,
    PRACTICE_SOURCE_SKILL,
    SESSION_KIND_MAIN,
    SESSION_KIND_SUBAGENT,
    SESSION_KIND_UNKNOWN,
    PracticeSourceRow,
    _classify_practice_family,
    _classify_session_kind,
    _extract_practice_rows,
    classify_codex_history,
)

WORKSPACE_ROOT, _SCRIPTS_DIR, ABS_SRC = find_repo_paths()
ABS_SCRIPT = _SCRIPTS_DIR / "metrics_cli.py"


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


# --- Practice-event classifier: unit tests -----------------------------------


def test_classify_practice_family_agent_catalog() -> None:
    assert _classify_practice_family(PRACTICE_SOURCE_AGENT, "Explore") == PRACTICE_FAMILY_DISCOVERY
    assert _classify_practice_family(PRACTICE_SOURCE_AGENT, "Plan") == PRACTICE_FAMILY_PLANNING
    assert (
        _classify_practice_family(PRACTICE_SOURCE_AGENT, "pr-review-toolkit:code-reviewer")
        == PRACTICE_FAMILY_CODE_REVIEW
    )


def test_classify_practice_family_skill_catalog() -> None:
    assert (
        _classify_practice_family(PRACTICE_SOURCE_SKILL, "commit-commands:commit")
        == PRACTICE_FAMILY_COMMIT_WORKFLOW
    )
    assert (
        _classify_practice_family(PRACTICE_SOURCE_SKILL, "code-review:code-review")
        == PRACTICE_FAMILY_CODE_REVIEW
    )


def test_classify_practice_family_unknown_returns_other() -> None:
    assert _classify_practice_family(PRACTICE_SOURCE_AGENT, "novel-agent") == PRACTICE_FAMILY_OTHER
    assert _classify_practice_family(PRACTICE_SOURCE_SKILL, "novel-skill") == PRACTICE_FAMILY_OTHER
    # Unknown source_kind also falls through safely.
    assert _classify_practice_family("unknown", "Explore") == PRACTICE_FAMILY_OTHER


def test_practice_classifier_version_is_stable() -> None:
    assert PRACTICE_EVENT_CLASSIFIER_VERSION.startswith("v1-")
    assert len(PRACTICE_EVENT_CLASSIFIER_VERSION) == len("v1-") + 8


def test_extract_practice_rows_emits_rows_for_agent_and_skill() -> None:
    raw_payload = {
        "message": {
            "content": [
                {"type": "text", "text": "planning"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Agent",
                    "input": {"subagent_type": "Explore", "description": "find files"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "Skill",
                    "input": {"skill": "commit-commands:commit"},
                },
                # Non-classifiable tool_use is ignored.
                {"type": "tool_use", "id": "toolu_3", "name": "Read", "input": {}},
            ]
        }
    }
    rows = _extract_practice_rows(
        PracticeSourceRow(
            event_id="evt-abc",
            session_path="/t/sess.jsonl",
            thread_id="t-1",
            source_path="src",
            event_index=3,
            timestamp="2026-04-19T12:00:00Z",
            raw_json=json.dumps(raw_payload),
        ),
        classifier_version=PRACTICE_EVENT_CLASSIFIER_VERSION,
        classified_at="2026-04-19T12:00:01Z",
    )
    assert len(rows) == 2
    # Row tuple: (pk, session, thread, source, event_index, timestamp,
    # tool_use_id, source_kind, practice_name, family, version, classified_at, raw)
    pks = [r[0] for r in rows]
    assert pks[0].startswith("evt-abc:")
    assert pks[1].startswith("evt-abc:")
    assert pks[0] != pks[1]
    assert rows[0][7] == PRACTICE_SOURCE_AGENT
    assert rows[0][8] == "Explore"
    assert rows[0][9] == PRACTICE_FAMILY_DISCOVERY
    assert rows[1][7] == PRACTICE_SOURCE_SKILL
    assert rows[1][8] == "commit-commands:commit"
    assert rows[1][9] == PRACTICE_FAMILY_COMMIT_WORKFLOW


def test_extract_practice_rows_on_malformed_json_returns_empty() -> None:
    rows = _extract_practice_rows(
        PracticeSourceRow(
            event_id="e",
            session_path="p",
            thread_id=None,
            source_path="s",
            event_index=0,
            timestamp=None,
            raw_json="{not json",
        ),
        classifier_version="v1-00000000",
        classified_at="2026-04-19T00:00:00Z",
    )
    assert rows == []


def test_extract_practice_rows_agent_without_subagent_type_falls_back() -> None:
    # Matches the 35 'Agent' rows in the real warehouse with no subagent_type —
    # we still emit a row so the count survives, but family is 'other'.
    payload = {
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Agent", "input": {}}]}
    }
    rows = _extract_practice_rows(
        PracticeSourceRow(
            event_id="e",
            session_path="p",
            thread_id="t",
            source_path="s",
            event_index=0,
            timestamp=None,
            raw_json=json.dumps(payload),
        ),
        classifier_version=PRACTICE_EVENT_CLASSIFIER_VERSION,
        classified_at="2026-04-19T00:00:00Z",
    )
    assert len(rows) == 1
    assert rows[0][8] == "<missing>"
    assert rows[0][9] == PRACTICE_FAMILY_OTHER


# --- End-to-end: practice events populated from ingested warehouse ----------


def _write_claude_session_with_tool_uses(
    root: Path,
    *,
    session_id: str,
    tool_uses: list[dict],
) -> Path:
    """Create a minimal ~/.claude layout with an assistant message containing tool_uses."""
    import json as _json

    cwd = str(root / "myproject")
    claude_root = root / "claude-source"
    encoded = cwd.replace("/", "-")
    project_dir = claude_root / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)

    user_line = _json.dumps({
        "type": "user",
        "uuid": "u-1",
        "parentUuid": None,
        "sessionId": session_id,
        "timestamp": "2026-04-01T10:00:00.000Z",
        "cwd": cwd,
        "version": "2.1.0",
        "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
    })
    assistant_line = _json.dumps({
        "type": "assistant",
        "uuid": "a-1",
        "parentUuid": "u-1",
        "sessionId": session_id,
        "timestamp": "2026-04-01T10:00:01.000Z",
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "ok"}, *tool_uses],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    })
    (project_dir / f"{session_id}.jsonl").write_text(
        user_line + "\n" + assistant_line + "\n", encoding="utf-8"
    )
    return claude_root


def test_classify_populates_derived_practice_events_end_to_end(repo: Path) -> None:
    import json as _json

    session_id = "dddd0000-0000-0000-0000-000000000001"
    tool_uses = [
        {
            "type": "tool_use",
            "id": "tu-1",
            "name": "Agent",
            "input": {"subagent_type": "Explore", "description": "discover"},
        },
        {
            "type": "tool_use",
            "id": "tu-2",
            "name": "Skill",
            "input": {"skill": "commit-commands:commit"},
        },
    ]
    claude_root = _write_claude_session_with_tool_uses(
        repo, session_id=session_id, tool_uses=tool_uses
    )
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
        ).returncode == 0
    )
    assert run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path)).returncode == 0

    summary = classify_codex_history(warehouse_path=warehouse_path)
    assert summary.practice_events_total == 2
    families = dict(summary.practice_events_by_family)
    assert families[PRACTICE_FAMILY_DISCOVERY] == 1
    assert families[PRACTICE_FAMILY_COMMIT_WORKFLOW] == 1
    assert summary.practice_event_classifier_version == PRACTICE_EVENT_CLASSIFIER_VERSION

    # Second run is idempotent — no duplicates.
    classify_codex_history(warehouse_path=warehouse_path)
    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM derived_practice_events").fetchone()[0]
        rows = conn.execute(
            "SELECT source_kind, practice_name, practice_family FROM derived_practice_events ORDER BY practice_name"
        ).fetchall()
    assert count == 2
    by_name = {row["practice_name"]: row for row in rows}
    assert by_name["Explore"]["source_kind"] == PRACTICE_SOURCE_AGENT
    assert by_name["Explore"]["practice_family"] == PRACTICE_FAMILY_DISCOVERY
    assert by_name["commit-commands:commit"]["source_kind"] == PRACTICE_SOURCE_SKILL
    assert by_name["commit-commands:commit"]["practice_family"] == PRACTICE_FAMILY_COMMIT_WORKFLOW
    # raw_json is valid JSON for every row.
    with sqlite3.connect(warehouse_path) as conn:
        for (raw,) in conn.execute("SELECT raw_json FROM derived_practice_events"):
            assert _json.loads(raw)["classifier_version"] == PRACTICE_EVENT_CLASSIFIER_VERSION


def test_classify_cli_reports_practice_events(repo: Path) -> None:
    session_id = "eeee0000-0000-0000-0000-000000000001"
    tool_uses = [
        {"type": "tool_use", "id": "tu-1", "name": "Agent",
         "input": {"subagent_type": "Explore", "description": "d"}},
    ]
    claude_root = _write_claude_session_with_tool_uses(
        repo, session_id=session_id, tool_uses=tool_uses
    )
    warehouse_path = repo / "metrics" / ".ai-agents-metrics" / "warehouse.db"

    run_cmd(repo, "history-ingest", "--source", "claude", "--source-root",
            str(claude_root), "--warehouse-path", str(warehouse_path))
    run_cmd(repo, "history-normalize", "--warehouse-path", str(warehouse_path))

    result = run_cmd(repo, "history-classify", "--warehouse-path", str(warehouse_path))
    assert result.returncode == 0, result.stderr
    assert "Practice events: 1" in result.stdout
    assert f"{PRACTICE_FAMILY_DISCOVERY}=1" in result.stdout


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
