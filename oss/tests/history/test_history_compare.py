from __future__ import annotations

import json
import sqlite3
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from test_history_ingest import run_cmd

from ai_agents_metrics import commands
from ai_agents_metrics.history.compare import (
    HistoryCompareFinding,
    HistoryCompareProjectRow,
    HistoryCompareReport,
    WarehouseScopeSummary,
    render_history_compare_report,
    render_history_compare_report_json,
)

if TYPE_CHECKING:
    import pytest


class _FakeRuntime:
    def __init__(self, report: HistoryCompareReport) -> None:
        self.report = report

    def compare_metrics_to_history(
        self,
        data: dict[str, object],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
    ) -> HistoryCompareReport:
        assert data == {}
        assert warehouse_path == Path("/warehouse.sqlite")
        assert cwd == Path("/repo")
        assert metrics_path == Path("/metrics.json")
        return self.report

    def render_history_compare_report(self, report: HistoryCompareReport) -> str:
        return render_history_compare_report(report)

    def render_history_compare_report_json(self, report: HistoryCompareReport) -> str:
        return render_history_compare_report_json(report)

    def load_metrics(self, path: Path) -> dict[str, object]:
        assert path == Path("/metrics.json")
        return {}


def test_render_history_compare_report_json_includes_summary_payload() -> None:
    report = HistoryCompareReport(
        metrics_path=Path("/metrics.json"),
        warehouse_path=Path("/warehouse.sqlite"),
        cwd=Path("/repo"),
        ledger_goal_count=4,
        ledger_closed_goal_count=3,
        ledger_success_count=2,
        ledger_fail_count=1,
        ledger_attempts_total=5,
        ledger_attempts_gt_one=1,
        ledger_known_token_successes=2,
        ledger_known_breakdown_successes=1,
        ledger_total_tokens_known=1234,
        warehouse_global=WarehouseScopeSummary(
            projects=2,
            threads=5,
            attempts=8,
            retry_threads=1,
            transcript_threads=5,
            usage_threads=4,
            input_tokens=111,
            cached_input_tokens=22,
            output_tokens=33,
            total_tokens=166,
        ),
        warehouse_project=WarehouseScopeSummary(
            projects=1,
            threads=2,
            attempts=3,
            retry_threads=0,
            transcript_threads=2,
            usage_threads=2,
            input_tokens=44,
            cached_input_tokens=5,
            output_tokens=6,
            total_tokens=55,
        ),
        warehouse_projects=[
            HistoryCompareProjectRow(
                project_cwd="/repo",
                threads=2,
                attempts=3,
                retry_threads=0,
                message_count=4,
                usage_event_count=2,
                log_count=1,
                timeline_event_count=5,
                total_tokens=55,
            )
        ],
        findings=[
            HistoryCompareFinding(
                category="subset_scope",
                message="project slice is smaller than the ledger",
            )
        ],
    )

    rendered = render_history_compare_report_json(report)
    payload = json.loads(rendered)

    assert payload["ledger"]["goal_count"] == 4
    assert payload["warehouse_global"]["total_tokens"] == 166
    assert payload["warehouse_projects"][0]["project_cwd"] == "/repo"
    assert payload["findings"][0]["category"] == "subset_scope"


def test_handle_compare_metrics_to_history_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        HistoryCompareReport(
            metrics_path=Path("/metrics.json"),
            warehouse_path=Path("/warehouse.sqlite"),
            cwd=Path("/repo"),
            ledger_goal_count=1,
            ledger_closed_goal_count=1,
            ledger_success_count=1,
            ledger_fail_count=0,
            ledger_attempts_total=1,
            ledger_attempts_gt_one=0,
            ledger_known_token_successes=0,
            ledger_known_breakdown_successes=0,
            ledger_total_tokens_known=0,
            warehouse_global=WarehouseScopeSummary(
                projects=1,
                threads=1,
                attempts=1,
                retry_threads=0,
                transcript_threads=1,
                usage_threads=0,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
            warehouse_project=WarehouseScopeSummary(
                projects=1,
                threads=1,
                attempts=1,
                retry_threads=0,
                transcript_threads=1,
                usage_threads=0,
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
            warehouse_projects=[],
            findings=[],
        )
    )

    exit_code = commands.handle_compare_metrics_to_history(
        Namespace(metrics_path="/metrics.json", warehouse_path="/warehouse.sqlite", cwd="/repo", json=True),
        runtime,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ledger"]["goal_count"] == 1



# ---------------------------------------------------------------------------
# history-compare CLI — missing warehouse
# ---------------------------------------------------------------------------


def test_history_compare_rejects_missing_warehouse(tmp_path: Path) -> None:
    warehouse_path = tmp_path / "missing.sqlite"

    result = run_cmd(tmp_path, "history-compare", "--warehouse-path", str(warehouse_path))

    assert result.returncode == 1
    assert f"Warehouse does not exist: {warehouse_path}" in result.stderr
    assert "history-update" in result.stderr


# ---------------------------------------------------------------------------
# read_history_signals
# ---------------------------------------------------------------------------

from ai_agents_metrics.history.compare import read_history_signals  # noqa: E402


def test_read_history_signals_absent_warehouse(tmp_path: Path) -> None:
    signals = read_history_signals(tmp_path / "missing.sqlite", tmp_path, {"goals": []})
    assert signals is None


def _make_warehouse_with_project(tmp_path_str: str, project_cwd: str, *, threads: int, retry_threads: int) -> Path:
    """Create a minimal warehouse with a single derived_projects row."""
    import sqlite3

    warehouse = Path(tmp_path_str) / "warehouse.sqlite"
    with sqlite3.connect(warehouse) as conn:
        conn.execute(
            """
            CREATE TABLE derived_goals (
                thread_id TEXT PRIMARY KEY,
                cwd TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                session_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT,
                last_seen_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_projects (
                project_cwd TEXT PRIMARY KEY,
                parent_project_cwd TEXT,
                thread_count INTEGER NOT NULL,
                retry_thread_count INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                usage_event_count INTEGER NOT NULL DEFAULT 0,
                log_count INTEGER NOT NULL DEFAULT 0,
                timeline_event_count INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER,
                raw_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "INSERT INTO derived_projects (project_cwd, parent_project_cwd, thread_count, retry_thread_count) VALUES (?,?,?,?)",
            (project_cwd, project_cwd, threads, retry_threads),
        )
        conn.commit()
    return warehouse


def test_read_history_signals_returns_project_stats(tmp_path: Path) -> None:
    cwd = tmp_path / "myproject"
    warehouse = _make_warehouse_with_project(str(tmp_path), str(cwd), threads=10, retry_threads=3)
    signals = read_history_signals(warehouse, cwd, {"goals": []})
    assert signals is not None
    assert signals.project_threads == 10
    assert signals.retry_threads == 3
    assert abs(signals.retry_rate - 0.3) < 0.001


def test_read_history_signals_worktree_merges_into_parent(tmp_path: Path) -> None:
    """Worktree row with parent_project_cwd set must be included in the parent's count."""
    import sqlite3

    cwd = tmp_path / "myproject"
    warehouse = tmp_path / "w.sqlite"
    with sqlite3.connect(warehouse) as conn:
        conn.execute(
            """
            CREATE TABLE derived_goals (thread_id TEXT PRIMARY KEY, cwd TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0, message_count INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 1, session_count INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT, last_seen_at TEXT)
            """
        )
        conn.execute(
            """
            CREATE TABLE derived_projects (
                project_cwd TEXT PRIMARY KEY, parent_project_cwd TEXT,
                thread_count INTEGER NOT NULL, retry_thread_count INTEGER NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0, message_count INTEGER NOT NULL DEFAULT 0,
                usage_event_count INTEGER NOT NULL DEFAULT 0, log_count INTEGER NOT NULL DEFAULT 0,
                timeline_event_count INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER,
                raw_json TEXT NOT NULL DEFAULT '{}')
            """
        )
        # Main project row
        conn.execute(
            "INSERT INTO derived_projects VALUES (?,?,?,?,0,0,0,0,0,NULL,'{}')",
            (str(cwd), str(cwd), 5, 1),
        )
        # Worktree row pointing to same parent
        worktree_cwd = str(cwd) + "/.claude/worktrees/foo"
        conn.execute(
            "INSERT INTO derived_projects VALUES (?,?,?,?,0,0,0,0,0,NULL,'{}')",
            (worktree_cwd, str(cwd), 3, 2),
        )
        conn.commit()

    signals = read_history_signals(warehouse, cwd, {"goals": []})
    assert signals is not None
    assert signals.project_threads == 8   # 5 + 3 merged
    assert signals.retry_threads == 3     # 1 + 2 merged


def test_read_history_signals_fallback_to_all_projects(tmp_path: Path) -> None:
    """When cwd doesn't match any project, fall back to all-projects view."""
    cwd = tmp_path / "empty"
    warehouse = _make_warehouse_with_project(str(tmp_path), "/other/project", threads=5, retry_threads=2)
    signals = read_history_signals(warehouse, cwd, {"goals": []})
    assert signals is not None
    assert signals.project_threads == 5
    assert signals.retry_threads == 2
    assert signals.retry_rate == 0.4
    assert signals.is_all_projects is True


def test_read_history_signals_no_data_returns_zero(tmp_path: Path) -> None:
    """When warehouse has derived tables but zero projects, return zero rate."""
    cwd = tmp_path / "empty"
    warehouse = tmp_path / "warehouse.sqlite"
    with sqlite3.connect(warehouse) as conn:
        conn.execute(
            "CREATE TABLE derived_projects "
            "(project_cwd TEXT, parent_project_cwd TEXT, thread_count INT, retry_thread_count INT)"
        )
        conn.execute("CREATE TABLE derived_goals (cwd TEXT, first_seen_at TEXT, last_seen_at TEXT)")
    signals = read_history_signals(warehouse, cwd, {"goals": []})
    assert signals is not None
    assert signals.project_threads == 0
    assert signals.retry_rate == 0.0
    assert signals.is_all_projects is False
