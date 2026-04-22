#!/usr/bin/env python3
"""Bootstrap shim: loads ``ai_agents_metrics.cli`` with a repo-local sys.path."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def _load_cli_module() -> ModuleType:
    repo_src_path = Path(__file__).resolve().parents[1] / "src"
    if repo_src_path.exists():
        sys.path.insert(0, str(repo_src_path))

    # Deferred import: the sys.path manipulation above must run before the
    # package can be resolved when the shim is invoked without the package
    # installed.
    import ai_agents_metrics.cli as cli  # pylint: disable=import-outside-toplevel

    return cli


_CLI_MODULE = _load_cli_module()
main = _CLI_MODULE.main
globals().update(
    {
        name: getattr(_CLI_MODULE, name)
        for name in dir(_CLI_MODULE)
        if not name.startswith("_") and name not in globals()
    }
)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
