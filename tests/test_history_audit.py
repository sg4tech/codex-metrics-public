from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from ai_agents_metrics import commands
from ai_agents_metrics.history.audit import (
    AuditCandidate,
    AuditReport,
    render_audit_report,
    render_audit_report_json,
)


class _FakeRuntime:
    def __init__(self, report: AuditReport) -> None:
        self.report = report

    def audit_history(self, data: dict[str, object]) -> AuditReport:
        assert data == {}
        return self.report

    def render_audit_report(self, report: AuditReport) -> str:
        return render_audit_report(report)

    def render_audit_report_json(self, report: AuditReport) -> str:
        return render_audit_report_json(report)

    def load_metrics(self, path: Path) -> dict[str, object]:
        assert path == Path("/metrics.json")
        return {}


def test_render_audit_report_json_includes_candidate_payload() -> None:
    report = AuditReport(
        candidates=[
            AuditCandidate(
                category="likely_miss",
                goal_id="CODEX-1",
                goal_type="product",
                status="fail",
                title="example",
                reason="explicit failed goal",
                suggested_result_fit="miss",
            )
        ]
    )

    rendered = render_audit_report_json(report)
    payload = json.loads(rendered)

    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["goal_id"] == "CODEX-1"
    assert payload["candidates"][0]["suggested_result_fit"] == "miss"


def test_handle_audit_history_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        AuditReport(
            candidates=[
                AuditCandidate(
                    category="likely_partial_fit",
                    goal_id="CODEX-2",
                    goal_type="product",
                    status="success",
                    title="retry",
                    reason="success required 2 attempts",
                    suggested_result_fit="partial_fit",
                )
            ]
        )
    )

    exit_code = commands.handle_audit_history(
        Namespace(metrics_path="/metrics.json", json=True),
        runtime,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["goal_id"] == "CODEX-2"
