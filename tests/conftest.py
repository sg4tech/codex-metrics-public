from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Ensure oss/tests/ is importable by its real path so that cross-test imports
# like `from test_history_ingest import ...` work regardless of whether tests
# run from oss/ directly or from the root repo via the tests/public/ symlink.
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)


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
