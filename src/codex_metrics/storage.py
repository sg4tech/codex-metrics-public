from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

LOCKFILE_SUFFIX = ".lock"


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _immutability_command() -> tuple[list[str], list[str]] | None:
    if os.name != "posix":
        return None
    sysname = os.uname().sysname
    if sysname in {"Darwin", "FreeBSD", "OpenBSD", "NetBSD"}:
        command = "chflags"
        commands = (["chflags", "nouchg"], ["chflags", "uchg"])
    elif sysname == "Linux":
        command = "chattr"
        commands = (["chattr", "-i"], ["chattr", "+i"])
    else:
        return None

    if shutil.which(command) is None:
        return None

    return commands


def _run_file_immutability_command(command: list[str], path: Path) -> None:
    subprocess.run([*command, str(path)], check=True, capture_output=True, text=True)


@contextlib.contextmanager
def metrics_file_immutability_guard(path: Path) -> Any:
    commands = _immutability_command()
    if commands is None:
        yield
        return

    unlock_command, lock_command = commands
    path_exists = path.exists()
    if path_exists:
        _run_file_immutability_command(unlock_command, path)
    try:
        yield
    finally:
        if path.exists():
            _run_file_immutability_command(lock_command, path)


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


def save_metrics(path: Path, data: dict[str, Any]) -> None:
    with metrics_file_immutability_guard(path):
        ensure_parent_dir(path)
        data_to_save = dict(data)
        data_to_save.pop("tasks", None)
        serialized = json.dumps(data_to_save, ensure_ascii=False, indent=2) + "\n"
        atomic_write_text(path, serialized)


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
