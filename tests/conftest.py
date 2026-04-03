from __future__ import annotations

from pathlib import Path

import pytest

from codex_metrics import file_immutability


@pytest.fixture(autouse=True)
def unlock_tmp_path_immutability(tmp_path: Path) -> Path:
    yield tmp_path

    immutability_commands = file_immutability.DEFAULT_FILE_IMMUTABILITY_BACKEND.command_pair()
    if immutability_commands is None or not tmp_path.exists():
        return

    unlock_command, _ = immutability_commands
    candidates = [tmp_path, *sorted(tmp_path.rglob("*"), reverse=True)]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            file_immutability.DEFAULT_FILE_IMMUTABILITY_BACKEND.run_command(unlock_command, candidate)
        except Exception:
            pass
