from __future__ import annotations

import tomllib
from pathlib import Path


def _load_paths() -> tuple[Path, Path, Path]:
    for parent in Path(__file__).resolve().parents:
        cfg = parent / "pyproject.toml"
        if not cfg.exists():
            continue
        with cfg.open("rb") as f:
            data = tomllib.load(f)
        ct = data.get("tool", {}).get("codex_tests")
        if ct:
            root = parent
            return root, root / ct["scripts"], root / ct["src"]
    raise RuntimeError("No [tool.codex_tests] section found in any pyproject.toml")


REPO_ROOT, ABS_SCRIPTS_DIR, ABS_SRC_DIR = _load_paths()
