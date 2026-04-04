from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from codex_metrics import commands
from codex_metrics.history_compare import (
    HistoryCompareFinding,
    HistoryCompareProjectRow,
    HistoryCompareReport,
    WarehouseScopeSummary,
    render_history_compare_report,
    render_history_compare_report_json,
)


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

