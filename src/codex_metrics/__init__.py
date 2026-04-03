"""codex-metrics package."""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

__all__ = ["__version__"]

_BASE_VERSION = "0.2.1"
_PACKAGE_NAME = "codex-metrics"


def _is_source_layout() -> bool:
    current = Path(__file__).resolve()
    return len(current.parents) >= 2 and current.parents[1].name == "src"


def _find_repo_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return parent
    return None


def _run_git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _version_from_git(repo_root: Path) -> str | None:
    commit_count = _run_git(repo_root, "rev-list", "--count", "HEAD")
    commit_sha = _run_git(repo_root, "rev-parse", "--short", "HEAD")
    if commit_count is None or commit_sha is None:
        return None

    dirty_output = _run_git(repo_root, "status", "--porcelain", "--untracked-files=no")
    dirty_suffix = ".dirty" if dirty_output else ""
    return f"{_BASE_VERSION}.dev{commit_count}+g{commit_sha}{dirty_suffix}"


def _resolve_version() -> str:
    repo_root = _find_repo_root()
    if repo_root is not None:
        git_version = _version_from_git(repo_root)
        if git_version is not None:
            return git_version

    if _is_source_layout():
        return _BASE_VERSION

    try:
        return installed_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return _BASE_VERSION


__version__ = _resolve_version()
