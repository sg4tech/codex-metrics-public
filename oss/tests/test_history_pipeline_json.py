from __future__ import annotations

import json
from argparse import Namespace
from contextlib import nullcontext
from pathlib import Path

import pytest

from ai_agents_metrics import commands
from ai_agents_metrics.history_derive import DeriveSummary, render_derive_summary_json
from ai_agents_metrics.history_ingest import IngestSummary, render_ingest_summary_json
from ai_agents_metrics.history_normalize import NormalizeSummary, render_normalize_summary_json


class _FakeRuntime:
    def __init__(
        self,
        *,
        ingest_summary: IngestSummary,
        normalize_summary: NormalizeSummary,
        derive_summary: DeriveSummary,
    ) -> None:
        self.ingest_summary = ingest_summary
        self.normalize_summary = normalize_summary
        self.derive_summary = derive_summary

    def metrics_mutation_lock(self, metrics_path: Path):
        return nullcontext()

    def ingest_codex_history(self, source_root: Path, warehouse_path: Path, source: str = "codex") -> IngestSummary:
        assert source_root == Path("/source")
        assert warehouse_path == Path("/warehouse.sqlite")
        return self.ingest_summary

    def normalize_codex_history(self, warehouse_path: Path) -> NormalizeSummary:
        assert warehouse_path == Path("/warehouse.sqlite")
        return self.normalize_summary

    def derive_codex_history(self, warehouse_path: Path) -> DeriveSummary:
        assert warehouse_path == Path("/warehouse.sqlite")
        return self.derive_summary

    def render_ingest_summary_json(self, summary: IngestSummary) -> str:
        return render_ingest_summary_json(summary)

    def render_normalize_summary_json(self, summary: NormalizeSummary) -> str:
        return render_normalize_summary_json(summary)

    def render_derive_summary_json(self, summary: DeriveSummary) -> str:
        return render_derive_summary_json(summary)


def test_render_history_pipeline_json_summaries() -> None:
    ingest = IngestSummary(
        source_root=Path("/source"),
        warehouse_path=Path("/warehouse.sqlite"),
        scanned_files=1,
        imported_files=1,
        skipped_files=0,
        projects=2,
        threads=3,
        sessions=4,
        session_events=5,
        token_count_events=6,
        token_usage_events=7,
        input_tokens=8,
        cached_input_tokens=9,
        output_tokens=10,
        reasoning_output_tokens=11,
        total_tokens=12,
        messages=13,
        logs=14,
    )
    ingest_payload = json.loads(render_ingest_summary_json(ingest))
    assert ingest_payload["projects"] == 2
    assert ingest_payload["total_tokens"] == 12

    normalize = NormalizeSummary(
        warehouse_path=Path("/warehouse.sqlite"),
        projects=2,
        threads=3,
        sessions=4,
        messages=5,
        usage_events=6,
        logs=7,
    )
    normalize_payload = json.loads(render_normalize_summary_json(normalize))
    assert normalize_payload["usage_events"] == 6

    derive = DeriveSummary(
        warehouse_path=Path("/warehouse.sqlite"),
        projects=2,
        goals=3,
        attempts=4,
        timeline_events=5,
        retry_chains=6,
        message_facts=7,
        session_usage=8,
    )
    derive_payload = json.loads(render_derive_summary_json(derive))
    assert derive_payload["retry_chains"] == 6


def test_handle_history_pipeline_commands_print_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        ingest_summary=IngestSummary(
            source_root=Path("/source"),
            warehouse_path=Path("/warehouse.sqlite"),
            scanned_files=1,
            imported_files=1,
            skipped_files=0,
            projects=2,
            threads=3,
            sessions=4,
            session_events=5,
            token_count_events=6,
            token_usage_events=7,
            input_tokens=8,
            cached_input_tokens=9,
            output_tokens=10,
            reasoning_output_tokens=11,
            total_tokens=12,
            messages=13,
            logs=14,
        ),
        normalize_summary=NormalizeSummary(
            warehouse_path=Path("/warehouse.sqlite"),
            projects=2,
            threads=3,
            sessions=4,
            messages=5,
            usage_events=6,
            logs=7,
        ),
        derive_summary=DeriveSummary(
            warehouse_path=Path("/warehouse.sqlite"),
            projects=2,
            goals=3,
            attempts=4,
            timeline_events=5,
            retry_chains=6,
            message_facts=7,
            session_usage=8,
        ),
    )

    assert (
        commands.handle_ingest_codex_history(
            Namespace(source_root="/source", warehouse_path="/warehouse.sqlite", json=True),
            runtime,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["projects"] == 2

    assert (
        commands.handle_normalize_codex_history(
            Namespace(warehouse_path="/warehouse.sqlite", json=True),
            runtime,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["logs"] == 7

    assert (
        commands.handle_derive_codex_history(
            Namespace(warehouse_path="/warehouse.sqlite", json=True),
            runtime,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["goals"] == 3
