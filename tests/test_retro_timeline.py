from __future__ import annotations

import json
from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path

import pytest

from ai_agents_metrics import commands
from ai_agents_metrics.retro_timeline import (
    RetroMetricWindow,
    RetroTimelineEvent,
    RetroTimelineRecord,
    RetroTimelineReport,
    RetroWindowDelta,
    render_retro_timeline_report,
    render_retro_timeline_report_json,
)


class _FakeRuntime:
    def __init__(self, report: RetroTimelineReport) -> None:
        self.report = report

    def recompute_summary(self, data: dict[str, object]) -> None:
        assert data == {}

    def metrics_mutation_lock(self, metrics_path: Path):
        assert metrics_path == Path("/warehouse.sqlite")
        return nullcontext()

    def derive_retro_timeline(
        self,
        data: dict[str, object],
        *,
        warehouse_path: Path,
        cwd: Path,
        metrics_path: Path,
        window_size: int,
    ) -> RetroTimelineReport:
        assert data == {}
        assert warehouse_path == Path("/warehouse.sqlite")
        assert cwd == Path("/repo")
        assert metrics_path == Path("/metrics.json")
        assert window_size == 3
        return self.report

    def render_retro_timeline_report(self, report: RetroTimelineReport) -> str:
        return render_retro_timeline_report(report)

    def render_retro_timeline_report_json(self, report: RetroTimelineReport) -> str:
        return render_retro_timeline_report_json(report)

    def load_metrics(self, path: Path) -> dict[str, object]:
        assert path == Path("/metrics.json")
        return {}


def test_render_retro_timeline_report_json_includes_record_payload() -> None:
    report = RetroTimelineReport(
        metrics_path=Path("/metrics.json"),
        warehouse_path=Path("/warehouse.sqlite"),
        cwd=Path("/repo"),
        window_size=3,
        events=[
            RetroTimelineEvent(
                retro_event_id="retro-event:example",
                message_id="msg-1",
                thread_id="thread-1",
                session_path="/tmp/session.jsonl",
                event_index=1,
                message_index=2,
                message_role="assistant",
                event_time="2026-04-04T10:00:00Z",
                event_date="2026-04-04",
                project_cwd="/repo",
                retro_file_path="docs/retros/2026-04-04-example.md",
                title="example",
                summary="summary",
                source_kind="message",
                raw_json='{"k":"v"}',
            )
        ],
        windows=[
            RetroMetricWindow(
                window_id="retro-event:example:before:3",
                retro_event_id="retro-event:example",
                window_side="before",
                window_strategy="product_goals_count",
                window_size=3,
                anchor_time="2026-04-04T10:00:00Z",
                window_start_time="2026-04-04T09:00:00Z",
                window_end_time="2026-04-04T09:30:00Z",
                product_goals_closed=2,
                product_success_rate=0.5,
                review_coverage=1.0,
                exact_fit_rate=0.5,
                partial_fit_rate=0.5,
                miss_rate=0.0,
                attempts_per_closed_product_goal=1.5,
                known_cost_per_success_usd=12.5,
                known_cost_coverage=1.0,
                failure_reason_summary='{"missing_context": 1}',
                goal_ids_json='["CODEX-1"]',
                raw_json='{"window":"before"}',
            )
        ],
        deltas=[
            RetroWindowDelta(
                retro_event_id="retro-event:example",
                window_strategy="product_goals_count",
                window_size=3,
                before_product_goals_closed=2,
                after_product_goals_closed=4,
                delta_product_success_rate=0.25,
                delta_exact_fit_rate=0.1,
                delta_partial_fit_rate=-0.1,
                delta_miss_rate=-0.05,
                delta_attempts_per_closed_product_goal=0.5,
                delta_known_cost_per_success_usd=1.5,
                delta_known_cost_coverage=0.2,
                raw_json='{"delta":true}',
            )
        ],
        records=[
            RetroTimelineRecord(
                event=RetroTimelineEvent(
                    retro_event_id="retro-event:example",
                    message_id="msg-1",
                    thread_id="thread-1",
                    session_path="/tmp/session.jsonl",
                    event_index=1,
                    message_index=2,
                    message_role="assistant",
                    event_time="2026-04-04T10:00:00Z",
                    event_date="2026-04-04",
                    project_cwd="/repo",
                    retro_file_path="docs/retros/2026-04-04-example.md",
                    title="example",
                    summary="summary",
                    source_kind="message",
                    raw_json='{"k":"v"}',
                ),
                before_window=RetroMetricWindow(
                    window_id="retro-event:example:before:3",
                    retro_event_id="retro-event:example",
                    window_side="before",
                    window_strategy="product_goals_count",
                    window_size=3,
                    anchor_time="2026-04-04T10:00:00Z",
                    window_start_time="2026-04-04T09:00:00Z",
                    window_end_time="2026-04-04T09:30:00Z",
                    product_goals_closed=2,
                    product_success_rate=0.5,
                    review_coverage=1.0,
                    exact_fit_rate=0.5,
                    partial_fit_rate=0.5,
                    miss_rate=0.0,
                    attempts_per_closed_product_goal=1.5,
                    known_cost_per_success_usd=12.5,
                    known_cost_coverage=1.0,
                    failure_reason_summary='{"missing_context": 1}',
                    goal_ids_json='["CODEX-1"]',
                    raw_json='{"window":"before"}',
                ),
                after_window=RetroMetricWindow(
                    window_id="retro-event:example:after:3",
                    retro_event_id="retro-event:example",
                    window_side="after",
                    window_strategy="product_goals_count",
                    window_size=3,
                    anchor_time="2026-04-04T10:00:00Z",
                    window_start_time="2026-04-04T10:30:00Z",
                    window_end_time="2026-04-04T11:00:00Z",
                    product_goals_closed=4,
                    product_success_rate=0.75,
                    review_coverage=1.0,
                    exact_fit_rate=0.6,
                    partial_fit_rate=0.4,
                    miss_rate=0.0,
                    attempts_per_closed_product_goal=2.0,
                    known_cost_per_success_usd=14.0,
                    known_cost_coverage=1.0,
                    failure_reason_summary='{"missing_context": 2}',
                    goal_ids_json='["CODEX-2"]',
                    raw_json='{"window":"after"}',
                ),
                delta=RetroWindowDelta(
                    retro_event_id="retro-event:example",
                    window_strategy="product_goals_count",
                    window_size=3,
                    before_product_goals_closed=2,
                    after_product_goals_closed=4,
                    delta_product_success_rate=0.25,
                    delta_exact_fit_rate=0.1,
                    delta_partial_fit_rate=-0.1,
                    delta_miss_rate=-0.05,
                    delta_attempts_per_closed_product_goal=0.5,
                    delta_known_cost_per_success_usd=1.5,
                    delta_known_cost_coverage=0.2,
                    raw_json='{"delta":true}',
                ),
            )
        ],
    )

    rendered = render_retro_timeline_report_json(report)
    payload = json.loads(rendered)

    assert payload["event_count"] == 1
    assert payload["record_count"] == 1
    assert payload["records"][0]["event"]["retro_event_id"] == "retro-event:example"
    assert payload["records"][0]["delta"]["delta_known_cost_coverage"] == 0.2


def test_handle_derive_retro_timeline_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        RetroTimelineReport(
            metrics_path=Path("/metrics.json"),
            warehouse_path=Path("/warehouse.sqlite"),
            cwd=Path("/repo"),
            window_size=3,
            events=[],
            windows=[],
            deltas=[],
            records=[],
        )
    )

    exit_code = commands.handle_derive_retro_timeline(
        Namespace(
            metrics_path="/metrics.json",
            warehouse_path="/warehouse.sqlite",
            cwd="/repo",
            window_size=3,
            json=True,
        ),
        runtime,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["window_size"] == 3
