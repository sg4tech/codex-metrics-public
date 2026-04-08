#!/usr/bin/env python3

import sys
from pathlib import Path


def _load_cli_module():
    repo_src_path = Path(__file__).resolve().parents[1] / "src"
    if repo_src_path.exists():
        sys.path.insert(0, str(repo_src_path))

    from codex_metrics import cli

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
        raise SystemExit(1)
