"""Git worktree inspection: StartedWorkReport and ActiveTaskResolution types."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MEANINGFUL_WORKTREE_DIRS = {"src", "tests", "docs", "scripts", "tools"}
MEANINGFUL_WORKTREE_FILES = {"AGENTS.md", "README.md", "Makefile", "pyproject.toml"}
LOW_SIGNAL_WORKTREE_PATHS = {
    Path("metrics/events.ndjson"),
    Path("docs/ai-agents-metrics.md"),
}


@dataclass(frozen=True)
class StartedWorkReport:
    started_work_detected: bool
    changed_paths: list[str]
    reason: str
    git_available: bool


@dataclass(frozen=True)
class ActiveTaskResolution:
    """Outcome of ensure_active_task — shared between cli.py and runtime_facade."""

    status: str
    goal_id: str | None
    message: str
    started_work_report: StartedWorkReport | None = None


def _run_git(cwd: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _normalize_worktree_path(path_text: str) -> str:
    cleaned = path_text.strip()
    if " -> " in cleaned:
        cleaned = cleaned.rsplit(" -> ", maxsplit=1)[-1]
    return cleaned


def _is_meaningful_worktree_path(path_text: str) -> bool:
    normalized = Path(path_text)
    if normalized in LOW_SIGNAL_WORKTREE_PATHS:
        return False
    parts = normalized.parts
    if not parts:
        return False
    if parts[0] in MEANINGFUL_WORKTREE_DIRS:
        return True
    return bool(len(parts) == 1 and parts[0] in MEANINGFUL_WORKTREE_FILES)


def detect_started_work(cwd: Path) -> StartedWorkReport:
    repo_root = _run_git(cwd, "rev-parse", "--show-toplevel")
    if repo_root is None:
        return StartedWorkReport(
            started_work_detected=False,
            changed_paths=[],
            reason="git is unavailable or the current directory is not inside a git repository",
            git_available=False,
        )

    status_output = _run_git(Path(repo_root), "status", "--porcelain", "--untracked-files=normal")
    if status_output is None:
        return StartedWorkReport(
            started_work_detected=False,
            changed_paths=[],
            reason="git status could not be read reliably",
            git_available=False,
        )

    changed_paths: list[str] = []
    meaningful_paths: list[str] = []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        path_text = _normalize_worktree_path(line[3:] if len(line) > 3 else line)
        if not path_text:
            continue
        changed_paths.append(path_text)
        if _is_meaningful_worktree_path(path_text):
            meaningful_paths.append(path_text)

    if meaningful_paths:
        return StartedWorkReport(
            started_work_detected=True,
            changed_paths=changed_paths,
            reason=f"meaningful git changes detected: {', '.join(meaningful_paths[:5])}",
            git_available=True,
        )

    if changed_paths:
        return StartedWorkReport(
            started_work_detected=False,
            changed_paths=changed_paths,
            reason="only low-signal changes are present, such as generated metrics or report outputs",
            git_available=True,
        )

    return StartedWorkReport(
        started_work_detected=False,
        changed_paths=[],
        reason="git working tree is clean",
        git_available=True,
    )
