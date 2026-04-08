"""codex-metrics package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

__all__ = ["__version__"]

try:
    __version__ = _installed_version("codex-metrics")
except PackageNotFoundError:
    try:
        from codex_metrics._version import (
            version as __version__,  # type: ignore[no-redef,import-untyped]
        )
    except ImportError:
        __version__ = "unknown"
