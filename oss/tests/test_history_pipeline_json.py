from __future__ import annotations

import json
from argparse import Namespace
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest

from ai_agents_metrics import commands
from ai_agents_metrics.history.derive import DeriveSummary, render_derive_summary_json
from ai_agents_metrics.history.ingest import IngestSummary, render_ingest_summary_json
from ai_agents_metrics.history.normalize import NormalizeSummary, render_normalize_summary_json


def _make_ingest_summary(source_root: str = "/source", warehouse: str = "/warehouse.sqlite") -> IngestSummary:
    return IngestSummary(
        source_root=Path(source_root),
        warehouse_path=Path(warehouse),
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


def _make_normalize_summary(warehouse: str = "/warehouse.sqlite") -> NormalizeSummary:
    return NormalizeSummary(
        warehouse_path=Path(warehouse),
        projects=2,
        threads=3,
        sessions=4,
        messages=5,
        usage_events=6,
        logs=7,
    )


def _make_derive_summary(warehouse: str = "/warehouse.sqlite") -> DeriveSummary:
    return DeriveSummary(
        warehouse_path=Path(warehouse),
        projects=2,
        goals=3,
        attempts=4,
        timeline_events=5,
        retry_chains=6,
        message_facts=7,
        session_usage=8,
    )


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


class _FakeRuntimeMultiSource:
    """Runtime that tracks which sources were ingested; used for source=all tests."""

    def __init__(
        self,
        *,
        ingest_summaries_by_source: dict[str, IngestSummary],
        normalize_summary: NormalizeSummary,
        derive_summary: DeriveSummary,
    ) -> None:
        self.ingest_summaries_by_source = ingest_summaries_by_source
        self.normalize_summary = normalize_summary
        self.derive_summary = derive_summary
        self.ingested_sources: list[str] = []

    def metrics_mutation_lock(self, metrics_path: Path):
        return nullcontext()

    def ingest_codex_history(self, source_root: Path, warehouse_path: Path, source: str = "codex") -> IngestSummary:
        self.ingested_sources.append(source)
        return self.ingest_summaries_by_source[source]

    def normalize_codex_history(self, warehouse_path: Path) -> NormalizeSummary:
        return self.normalize_summary

    def derive_codex_history(self, warehouse_path: Path) -> DeriveSummary:
        return self.derive_summary

    def render_ingest_summary_json(self, summary: IngestSummary) -> str:
        return render_ingest_summary_json(summary)

    def render_normalize_summary_json(self, summary: NormalizeSummary) -> str:
        return render_normalize_summary_json(summary)

    def render_derive_summary_json(self, summary: DeriveSummary) -> str:
        return render_derive_summary_json(summary)


def test_render_history_pipeline_json_summaries() -> None:
    ingest_payload = json.loads(render_ingest_summary_json(_make_ingest_summary()))
    assert ingest_payload["projects"] == 2
    assert ingest_payload["total_tokens"] == 12

    normalize_payload = json.loads(render_normalize_summary_json(_make_normalize_summary()))
    assert normalize_payload["usage_events"] == 6

    derive_payload = json.loads(render_derive_summary_json(_make_derive_summary()))
    assert derive_payload["retry_chains"] == 6


def test_handle_history_pipeline_commands_print_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        ingest_summary=_make_ingest_summary(),
        normalize_summary=_make_normalize_summary(),
        derive_summary=_make_derive_summary(),
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


def test_history_update_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        ingest_summary=_make_ingest_summary(),
        normalize_summary=_make_normalize_summary(),
        derive_summary=_make_derive_summary(),
    )
    result = commands.handle_history_update(
        Namespace(source="codex", source_root="/source", warehouse_path="/warehouse.sqlite", json=False),
        runtime,
    )
    assert result == 0
    out = capsys.readouterr().out
    assert "==> history-ingest" in out
    assert "==> history-normalize" in out
    assert "==> history-derive" in out
    assert "Done." in out


def test_history_update_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        ingest_summary=_make_ingest_summary(),
        normalize_summary=_make_normalize_summary(),
        derive_summary=_make_derive_summary(),
    )
    result = commands.handle_history_update(
        Namespace(source="codex", source_root="/source", warehouse_path="/warehouse.sqlite", json=True),
        runtime,
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ingest"]["codex"]["threads"] == 3
    assert payload["normalize"]["usage_events"] == 6
    assert payload["derive"]["retry_chains"] == 6


def test_history_update_no_source_reads_both(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """history-update without --source must read both ~/.codex and ~/.claude."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".claude").mkdir()

    codex_summary = replace(
        _make_ingest_summary(source_root=str(tmp_path / ".codex"), warehouse="/warehouse.sqlite"),
        threads=5,
    )
    claude_summary = replace(
        _make_ingest_summary(source_root=str(tmp_path / ".claude"), warehouse="/warehouse.sqlite"),
        threads=7,
    )

    runtime = _FakeRuntimeMultiSource(
        ingest_summaries_by_source={"codex": codex_summary, "claude": claude_summary},
        normalize_summary=_make_normalize_summary(),
        derive_summary=_make_derive_summary(),
    )
    result = commands.handle_history_update(
        Namespace(source=None, source_root=None, warehouse_path="/warehouse.sqlite", json=False),
        runtime,
    )
    assert result == 0
    assert runtime.ingested_sources == ["codex", "claude"]
    out = capsys.readouterr().out
    assert "==> history-ingest (codex)" in out
    assert "==> history-ingest (claude)" in out
    assert "==> history-normalize" in out
    assert "==> history-derive" in out
    assert "Done." in out


def test_history_update_no_source_one_missing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """history-update without --source skips a source whose directory does not exist."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".codex").mkdir()
    # ~/.claude intentionally absent

    codex_summary = _make_ingest_summary(source_root=str(tmp_path / ".codex"), warehouse="/warehouse.sqlite")

    runtime = _FakeRuntimeMultiSource(
        ingest_summaries_by_source={"codex": codex_summary},
        normalize_summary=_make_normalize_summary(),
        derive_summary=_make_derive_summary(),
    )
    result = commands.handle_history_update(
        Namespace(source=None, source_root=None, warehouse_path="/warehouse.sqlite", json=False),
        runtime,
    )
    assert result == 0
    assert runtime.ingested_sources == ["codex"]
    out = capsys.readouterr().out
    assert "==> history-ingest (codex)" in out
    assert "[skipped:" in out  # claude skipped message
    assert "==> history-normalize" in out
