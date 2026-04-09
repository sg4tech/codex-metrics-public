#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    build_root = repo_root / "build" / "standalone"
    dist_root = repo_root / "dist" / "standalone"
    config_root = build_root / ".pyinstaller"
    data_dir = repo_root / "src" / "ai_agents_metrics" / "data"
    add_data_separator = ";" if os.name == "nt" else ":"

    shutil.rmtree(build_root, ignore_errors=True)
    shutil.rmtree(dist_root, ignore_errors=True)
    build_root.mkdir(parents=True, exist_ok=True)
    dist_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "codex-metrics",
        "--paths",
        str(repo_root / "src"),
        "--specpath",
        str(build_root),
        "--add-data",
        f"{data_dir}{add_data_separator}ai_agents_metrics/data",
        "--distpath",
        str(dist_root),
        "--workpath",
        str(build_root),
        str(repo_root / "src" / "ai_agents_metrics" / "__main__.py"),
    ]
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(config_root)
    return subprocess.call(cmd, cwd=repo_root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
