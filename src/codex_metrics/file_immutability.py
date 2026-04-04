from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterator


class FileImmutabilityBackend:
    def command_pair(self) -> tuple[list[str], list[str]] | None:
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

    def run_command(self, command: list[str], path: Path) -> None:
        subprocess.run([*command, str(path)], check=True, capture_output=True, text=True)

    @contextlib.contextmanager
    def guard(self, path: Path) -> Iterator[None]:
        commands = self.command_pair()
        if commands is None:
            yield
            return

        unlock_command, lock_command = commands
        path_exists = path.exists()
        if path_exists:
            self.run_command(unlock_command, path)
        try:
            yield
        finally:
            if path.exists():
                self.run_command(lock_command, path)


DEFAULT_FILE_IMMUTABILITY_BACKEND = FileImmutabilityBackend()


@contextlib.contextmanager
def metrics_file_immutability_guard(
    path: Path,
    *,
    backend: FileImmutabilityBackend = DEFAULT_FILE_IMMUTABILITY_BACKEND,
) -> Iterator[None]:
    with backend.guard(path):
        yield
