from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from codex_metrics import commands
from codex_metrics.cost_audit import (
    CostAuditCandidate,
    CostAuditReport,
    render_cost_audit_report,
    render_cost_audit_report_json,
)


class _FakeRuntime:
    def __init__(self, report: CostAuditReport) -> None:
        self.report = report

    def audit_cost_coverage(
        self,
        data: dict[str, object],
        *,
        pricing_path: Path,
        codex_state_path: Path,
        codex_logs_path: Path,
        codex_thread_id: str | None,
        cwd: Path,
    ) -> CostAuditReport:
        assert data == {}
        assert pricing_path == Path("/pricing.json")
        assert codex_state_path == Path("/state.sqlite")
        assert codex_logs_path == Path("/logs.sqlite")
        assert codex_thread_id is None
        assert cwd == Path.cwd()
        return self.report

    def render_cost_audit_report(self, report: CostAuditReport) -> str:
        return render_cost_audit_report(report)

    def render_cost_audit_report_json(self, report: CostAuditReport) -> str:
        return render_cost_audit_report_json(report)

    def load_metrics(self, path: Path) -> dict[str, object]:
        assert path == Path("/metrics.json")
        return {}


def test_render_cost_audit_report_json_includes_candidate_payload() -> None:
    report = CostAuditReport(
        covered_goals=2,
        candidates=[
            CostAuditCandidate(
                category="sync_gap",
                goal_id="CODEX-3",
                goal_type="product",
                status="success",
                title="example",
                reason="recoverable Codex usage exists",
                started_at="2026-04-04T10:00:00Z",
                finished_at="2026-04-04T11:00:00Z",
                has_cost=False,
                has_tokens=True,
                suggested_next_action="Run sync-usage.",
            )
        ],
    )

    rendered = render_cost_audit_report_json(report)
    payload = json.loads(rendered)

    assert payload["covered_goals"] == 2
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["goal_id"] == "CODEX-3"
    assert payload["candidates"][0]["suggested_next_action"] == "Run sync-usage."


def test_handle_audit_cost_coverage_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        CostAuditReport(
            covered_goals=1,
            candidates=[
                CostAuditCandidate(
                    category="thread_unresolved",
                    goal_id="CODEX-4",
                    goal_type="product",
                    status="fail",
                    title="retry",
                    reason="no Codex thread could be resolved",
                    started_at=None,
                    finished_at=None,
                    has_cost=False,
                    has_tokens=False,
                    suggested_next_action="Pass --codex-thread-id.",
                )
            ],
        )
    )

    exit_code = commands.handle_audit_cost_coverage(
        Namespace(
            metrics_path="/metrics.json",
            pricing_path="/pricing.json",
            codex_state_path="/state.sqlite",
            codex_logs_path="/logs.sqlite",
            codex_thread_id=None,
            json=True,
        ),
        runtime,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["goal_id"] == "CODEX-4"
