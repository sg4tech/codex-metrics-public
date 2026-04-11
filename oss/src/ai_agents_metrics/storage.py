from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
import time
from pathlib import Path
from typing import Any

LOCKFILE_SUFFIX = ".lock"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    ensure_parent_dir(path)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(path)



def metrics_lock_path(metrics_path: Path) -> Path:
    return metrics_path.with_name(f"{metrics_path.name}{LOCKFILE_SUFFIX}")


@contextlib.contextmanager
def metrics_mutation_lock(metrics_path: Path) -> Any:
    lock_path = metrics_lock_path(metrics_path)
    ensure_parent_dir(lock_path)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        debug_sleep_seconds = float(os.environ.get("CODEX_METRICS_DEBUG_LOCK_HOLD_SECONDS", "0"))
        if debug_sleep_seconds > 0:
            time.sleep(debug_sleep_seconds)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
