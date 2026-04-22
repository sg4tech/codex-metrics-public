from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_agents_metrics.git_state import (  # noqa: E402
    _is_meaningful_worktree_path,
    _normalize_worktree_path,
    detect_started_work,
)

# ---------------------------------------------------------------------------
# _normalize_worktree_path
# ---------------------------------------------------------------------------


def test_normalize_worktree_path_plain() -> None:
    assert _normalize_worktree_path("src/foo.py") == "src/foo.py"


def test_normalize_worktree_path_strips_whitespace() -> None:
    assert _normalize_worktree_path("  src/foo.py  ") == "src/foo.py"


def test_normalize_worktree_path_resolves_rename() -> None:
    assert _normalize_worktree_path("old.py -> new.py") == "new.py"


# ---------------------------------------------------------------------------
# _is_meaningful_worktree_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path_text",
    [
        "src/ai_agents_metrics/cli.py",
        "tests/test_foo.py",
        "docs/architecture/README.md",
        "scripts/run.sh",
        "tools/ai-agents-metrics",
        "AGENTS.md",
        "README.md",
        "Makefile",
        "pyproject.toml",
    ],
)
def test_is_meaningful_worktree_path_returns_true(path_text: str) -> None:
    assert _is_meaningful_worktree_path(path_text) is True


@pytest.mark.parametrize(
    "path_text",
    [
        "metrics/events.ndjson",
        "docs/ai-agents-metrics.md",
    ],
)
def test_is_meaningful_worktree_path_returns_false_for_low_signal(path_text: str) -> None:
    assert _is_meaningful_worktree_path(path_text) is False


def test_is_meaningful_worktree_path_returns_false_for_empty() -> None:
    assert _is_meaningful_worktree_path("") is False


def test_is_meaningful_worktree_path_returns_false_for_unknown_top_level_file() -> None:
    assert _is_meaningful_worktree_path("random.txt") is False


# ---------------------------------------------------------------------------
# detect_started_work
# ---------------------------------------------------------------------------


def _make_git_mock(rev_parse_result: str | None, status_result: str | None):
    """Return a side_effect function for patching _run_git."""

    def _run_git(_cwd: Path, *args: str) -> str | None:
        if args[0] == "rev-parse":
            return rev_parse_result
        if args[0] == "status":
            return status_result
        return None

    return _run_git


def test_detect_started_work_git_unavailable() -> None:
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock(None, None)):
        report = detect_started_work(Path("/some/repo"))

    assert report.git_available is False
    assert report.started_work_detected is False


def test_detect_started_work_clean_tree() -> None:
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", "")):
        report = detect_started_work(Path("/repo"))

    assert report.git_available is True
    assert report.started_work_detected is False
    assert report.changed_paths == []


def test_detect_started_work_meaningful_changes() -> None:
    status = " M src/ai_agents_metrics/cli.py\n M tests/test_foo.py"
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", status)):
        report = detect_started_work(Path("/repo"))

    assert report.git_available is True
    assert report.started_work_detected is True
    assert "src/ai_agents_metrics/cli.py" in report.changed_paths


def test_detect_started_work_low_signal_only() -> None:
    status = " M metrics/events.ndjson\n M docs/ai-agents-metrics.md"
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", status)):
        report = detect_started_work(Path("/repo"))

    assert report.git_available is True
    assert report.started_work_detected is False
    assert len(report.changed_paths) == 2


def test_detect_started_work_mixed_changes() -> None:
    status = " M metrics/events.ndjson\n M src/ai_agents_metrics/domain.py"
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", status)):
        report = detect_started_work(Path("/repo"))

    assert report.started_work_detected is True
    assert "src/ai_agents_metrics/domain.py" in report.changed_paths


def test_detect_started_work_rename_parsed_correctly() -> None:
    status = "R  old.py -> src/new.py"
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", status)):
        report = detect_started_work(Path("/repo"))

    assert report.started_work_detected is True
    assert any("src/new.py" in p for p in report.changed_paths)


def test_detect_started_work_status_unavailable_after_rev_parse() -> None:
    """rev-parse succeeds but git status returns None → git_available=False."""
    with patch("ai_agents_metrics.git_state._run_git", side_effect=_make_git_mock("/repo", None)):
        report = detect_started_work(Path("/repo"))

    assert report.git_available is False
    assert report.started_work_detected is False
    assert report.changed_paths == []


# ---------------------------------------------------------------------------
# detect_started_work does NOT require importing from cli
# ---------------------------------------------------------------------------


def test_detect_started_work_importable_without_cli() -> None:
    """Verify git_state can be imported and used without importing cli."""
    import importlib

    git_state = importlib.import_module("ai_agents_metrics.git_state")
    assert hasattr(git_state, "detect_started_work")
    assert hasattr(git_state, "StartedWorkReport")
