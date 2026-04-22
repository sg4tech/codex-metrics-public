from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from ai_agents_metrics import commands
from ai_agents_metrics.public_boundary import (
    PublicBoundaryFinding,
    PublicBoundaryReport,
    load_public_boundary_rules,
    render_public_boundary_report,
    render_public_boundary_report_json,
    verify_public_boundary,
)

if TYPE_CHECKING:
    import pytest


def _write_rules(path: Path, *, marker_ignored_paths: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered_marker_ignored_paths = marker_ignored_paths or []
    marker_ignored_block = ""
    if rendered_marker_ignored_paths:
        quoted = ", ".join(f'"{value}"' for value in rendered_marker_ignored_paths)
        marker_ignored_block = f"marker_ignored_paths = [{quoted}]\n"
    path.write_text(
        """
allowed_roots = ["README.md", "docs", "src", "tests", "config"]
forbidden_paths = ["metrics", "docs/retros"]
forbidden_globs = ["docs/audits/**", "**/*.sqlite"]
forbidden_extensions = [".sqlite"]
forbidden_literal_markers = ["Internal only", "/Users/viktor/PycharmProjects/"]
forbidden_regex_markers = ["docs/retros/[0-9]{4}-[0-9]{2}-[0-9]{2}-"]
ignored_paths = [".git/**", "build/**"]
""".strip()
        + "\n"
        + marker_ignored_block
        ,
        encoding="utf-8",
    )


def test_load_public_boundary_rules_reads_repo_config() -> None:
    rules = load_public_boundary_rules(Path("config/public-boundary-rules.toml"))

    assert "src" in rules.allowed_roots
    assert "metrics" in rules.forbidden_paths
    assert "docs/private" in rules.forbidden_paths
    assert "/Users/[^/]+/PycharmProjects/" in rules.forbidden_regex_markers
    assert "tests/test_public_boundary.py" in rules.marker_ignored_paths


def test_verify_public_boundary_passes_for_clean_tree(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "README.md").write_text("Public docs only.\n", encoding="utf-8")
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "guide.md").write_text("Open-source usage guide.\n", encoding="utf-8")

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert report.files_scanned == 4
    assert report.findings == ()
    assert "passed" in render_public_boundary_report(report)


def test_verify_public_boundary_rejects_forbidden_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "docs" / "retros").mkdir(parents=True)
    (repo_root / "docs" / "retros" / "2026-04-04-retro.md").write_text("private retro\n", encoding="utf-8")

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert any(finding.kind == "forbidden_path" for finding in report.findings)
    assert any(finding.matched_rule == "docs/retros" for finding in report.findings)


def test_verify_public_boundary_rejects_unexpected_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "internal").mkdir(parents=True)
    (repo_root / "internal" / "notes.md").write_text("not public\n", encoding="utf-8")

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert any(finding.kind == "unexpected_root" for finding in report.findings)
    assert any(finding.matched_rule == "internal" for finding in report.findings)


def test_verify_public_boundary_rejects_forbidden_extension(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "docs").mkdir(parents=True)
    (repo_root / "docs" / "history.sqlite").write_text("not really sqlite\n", encoding="utf-8")

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert any(finding.kind == "forbidden_extension" for finding in report.findings)
    assert any(finding.matched_rule == ".sqlite" for finding in report.findings)


def test_verify_public_boundary_rejects_literal_marker_in_allowed_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "docs").mkdir(parents=True)
    (repo_root / "docs" / "guide.md").write_text(
        "Public intro\nInternal only\nrest\n",
        encoding="utf-8",
    )

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    marker_findings = [finding for finding in report.findings if finding.kind == "forbidden_marker"]
    assert marker_findings
    assert marker_findings[0].matched_rule == "Internal only"
    assert marker_findings[0].line == 2


def test_verify_public_boundary_rejects_regex_marker_in_allowed_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "docs").mkdir(parents=True)
    (repo_root / "docs" / "guide.md").write_text(
        "See docs/retros/2026-04-04-hidden-retro.md for more.\n",
        encoding="utf-8",
    )

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert any(
        finding.kind == "forbidden_marker"
        and finding.matched_rule == "docs/retros/[0-9]{4}-[0-9]{2}-[0-9]{2}-"
        for finding in report.findings
    )


def test_verify_public_boundary_ignores_configured_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path)
    (repo_root / "build").mkdir(parents=True)
    (repo_root / "build" / "snapshot.sqlite").write_text("ignored\n", encoding="utf-8")
    (repo_root / "README.md").write_text("clean\n", encoding="utf-8")

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert report.files_scanned == 2
    assert report.findings == ()


def test_verify_public_boundary_ignores_marker_scan_for_configured_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    rules_path = repo_root / "config" / "rules.toml"
    _write_rules(rules_path, marker_ignored_paths=["tests/leak-fixture.md"])
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "tests" / "leak-fixture.md").write_text(
        "Internal only\n/Users/viktor/PycharmProjects/codex-metrics\n",
        encoding="utf-8",
    )

    report = verify_public_boundary(repo_root=repo_root, rules_path=rules_path)

    assert report.findings == ()


class _FakeRuntime:
    def __init__(self, report: PublicBoundaryReport) -> None:
        self.report = report

    def verify_public_boundary(self, *, repo_root: Path, rules_path: Path) -> PublicBoundaryReport:
        assert repo_root == Path("/repo")
        assert rules_path == Path("/rules.toml")
        return self.report

    def render_public_boundary_report(self, report: PublicBoundaryReport) -> str:
        return render_public_boundary_report(report)

    def render_public_boundary_report_json(self, report: PublicBoundaryReport) -> str:
        return render_public_boundary_report_json(report)


def test_handle_verify_public_boundary_prints_success(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        PublicBoundaryReport(
            repo_root=Path("/repo"),
            rules_path=Path("/rules.toml"),
            files_scanned=3,
            findings=(),
        )
    )

    exit_code = commands.handle_verify_public_boundary(
        Namespace(repo_root="/repo", rules_path="/rules.toml"),
        runtime,
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "passed" in captured.out


def test_handle_verify_public_boundary_prints_failure(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        PublicBoundaryReport(
            repo_root=Path("/repo"),
            rules_path=Path("/rules.toml"),
            files_scanned=2,
            findings=(
                PublicBoundaryFinding(
                    kind="forbidden_path",
                    path="docs/retros/2026-04-04-retro.md",
                    message="path matches a forbidden private-only boundary rule",
                    matched_rule="docs/retros",
                ),
            ),
        )
    )

    exit_code = commands.handle_verify_public_boundary(
        Namespace(repo_root="/repo", rules_path="/rules.toml"),
        runtime,
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "failed" in captured.out


def test_handle_verify_public_boundary_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    runtime = _FakeRuntime(
        PublicBoundaryReport(
            repo_root=Path("/repo"),
            rules_path=Path("/rules.toml"),
            files_scanned=2,
            findings=(
                PublicBoundaryFinding(
                    kind="forbidden_path",
                    path="docs/retros/2026-04-04-retro.md",
                    message="path matches a forbidden private-only boundary rule",
                    matched_rule="docs/retros",
                ),
            ),
        )
    )

    exit_code = commands.handle_verify_public_boundary(
        Namespace(repo_root="/repo", rules_path="/rules.toml", json=True),
        runtime,
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert '"files_scanned": 2' in captured.out
    assert '"kind": "forbidden_path"' in captured.out
