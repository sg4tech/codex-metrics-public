"""chattr-style file immutability helpers used around ledger mutations."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator


class FileImmutabilityBackend:
    def __init__(self) -> None:
        self._pair_resolved = False
        self._pair: tuple[list[str], list[str]] | None = None

    def command_pair(self) -> tuple[list[str], list[str]] | None:
        if not self._pair_resolved:
            self._pair = self._resolve_command_pair()
            self._pair_resolved = True
        return self._pair

    def _resolve_command_pair(self) -> tuple[list[str], list[str]] | None:
        if os.name != "posix":
            return None
        sysname = os.uname().sysname
        if sysname in {"Darwin", "FreeBSD", "OpenBSD", "NetBSD"}:
            command = "chflags"
            commands: tuple[list[str], list[str]] = (["chflags", "nouchg"], ["chflags", "uchg"])
        elif sysname == "Linux":
            command = "chattr"
            commands = (["chattr", "-i"], ["chattr", "+i"])
        else:
            return None

        if shutil.which(command) is None:
            return None

        if not self._probe_permitted(commands):
            return None

        return commands

    def _probe_permitted(self, commands: tuple[list[str], list[str]]) -> bool:
        """Return True only if the immutability commands can actually be executed."""
        unlock_command, lock_command = commands
        fd, tmp_path = tempfile.mkstemp()
        os.close(fd)
        locked = False
        try:
            subprocess.run([*lock_command, tmp_path], check=True, capture_output=True)
            locked = True
            subprocess.run([*unlock_command, tmp_path], check=True, capture_output=True)
            locked = False
            return True
        except subprocess.CalledProcessError:
            return False
        finally:
            if locked:
                with contextlib.suppress(subprocess.CalledProcessError, OSError):
                    subprocess.run([*unlock_command, tmp_path], capture_output=True, check=False)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

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
