from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# Ensure oss/tests/ and every immediate test subdirectory are importable by
# their real paths so cross-test imports like `from test_history_ingest import
# ...` keep resolving after tests were grouped into subject-area subdirs.
_tests_dir = Path(__file__).resolve().parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))
for _sub in _tests_dir.iterdir():
    if _sub.is_dir() and not _sub.name.startswith((".", "__")):
        _sub_str = str(_sub)
        if _sub_str not in sys.path:
            sys.path.insert(0, _sub_str)

# Ensure oss/ is on sys.path so tests can `import scripts.*` regardless of
# whether pytest is invoked via `python -m pytest` (which adds cwd) or via
# the `pytest` console script (which does not). Previously tests only passed
# via the former; the latter raised ModuleNotFoundError for `scripts`.
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


@lru_cache(maxsize=1)
def find_repo_paths() -> tuple[Path, Path, Path]:
    """Locate the repo root, scripts/, and src/ via ``[tool.codex_tests]``.

    Walks up from this file until a ``pyproject.toml`` with a ``[tool.codex_tests]``
    section is found. Prefer this over ``Path(__file__).parents[N]`` so tests
    keep resolving paths correctly even when files move between subdirectories.
    """
    for parent in Path(__file__).resolve().parents:
        cfg = parent / "pyproject.toml"
        if not cfg.exists():
            continue
        with cfg.open("rb") as fh:
            codex_tests = tomllib.load(fh).get("tool", {}).get("codex_tests")
        if codex_tests:
            return parent, parent / codex_tests["scripts"], parent / codex_tests["src"]
    raise RuntimeError("No [tool.codex_tests] found in any ancestor pyproject.toml")


# Session-scoped baseline repo built once per test run; ``repo`` below copies
# from it with ``cp -rl`` (hardlinks) so per-test setup avoids re-running git
# five times. Previously each test dir duplicated a ``repo`` fixture that
# spawned ``git init`` + two ``git config`` + ``git add`` + ``git commit`` per
# test — under xdist parallel workers this was the dominant source of flakes
# at the 5s per-test pytest-timeout (the git subprocesses queue up under CPU
# contention and push normal in-process tests over the cliff).
@pytest.fixture(scope="session")
def _repo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    _workspace_root, _scripts_dir, abs_src = find_repo_paths()
    abs_script = _scripts_dir / "metrics_cli.py"
    pricing_source = _workspace_root / "pricing" / "model_pricing.json"

    template = tmp_path_factory.mktemp("repo_template")
    for name in ("src", "scripts", "docs", "metrics", "pricing"):
        (template / name).mkdir(parents=True, exist_ok=True)
    (template / "pricing" / "model_pricing.json").write_text(
        pricing_source.read_text(encoding="utf-8"), encoding="utf-8",
    )
    (template / "scripts" / "metrics_cli.py").write_text(
        abs_script.read_text(encoding="utf-8"), encoding="utf-8",
    )
    shutil.copytree(abs_src, template / "src", dirs_exist_ok=True)

    subprocess.run(["git", "init"], cwd=template, text=True, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "codex@example.com"],
        cwd=template, text=True, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Codex"],
        cwd=template, text=True, capture_output=True, check=True,
    )
    subprocess.run(["git", "add", "."], cwd=template, text=True, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=template, text=True, capture_output=True, check=True,
    )
    # Strip write bits so accidental writes to template-originated hardlinks
    # fail loudly with PermissionError instead of silently poisoning the
    # shared inode for every subsequent test. Directories stay writable so
    # tests can still add their own files.
    for path in template.rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode & 0o555)
    return template


@pytest.fixture
def repo(tmp_path: Path, _repo_template: Path) -> Path:
    """Per-test repo copy. ``cp -rl`` hardlinks from the session template."""
    subprocess.run(
        ["cp", "-rl", f"{_repo_template}/.", str(tmp_path)],
        check=True, capture_output=True,
    )
    return tmp_path


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    """Temporarily change working directory (safe within xdist workers)."""
    old = str(Path.cwd())
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def run_cli_inprocess(
    cwd: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Call the CLI main() in-process, returning a CompletedProcess-compatible result.

    Falls back to subprocess when CODEX_SUBPROCESS_COVERAGE is set (coverage
    requires a fresh interpreter to track per-invocation hits).
    """
    from ai_agents_metrics.cli import main

    old_argv = sys.argv
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    old_env: dict[str, str | None] = {}

    try:
        sys.argv = ["ai-agents-metrics", *args]

        if extra_env:
            for k, v in extra_env.items():
                old_env[k] = os.environ.get(k)
                os.environ[k] = v

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        with _chdir(cwd):
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            try:
                returncode = main()
                if returncode is None:
                    returncode = 0
            except SystemExit as exc:
                returncode = int(exc.code) if exc.code is not None else 0
            except ValueError as exc:
                # Mirror console_main() which catches ValueError only.
                print(f"Error: {exc}", file=stderr_buf)
                returncode = 1

        return subprocess.CompletedProcess(
            args=sys.argv,
            returncode=returncode,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
        )
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        if extra_env:
            for k in extra_env:
                orig = old_env.get(k)
                if orig is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = orig
