"""ai-agents-metrics package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

__all__ = ["__version__"]


def _resolve_version() -> str:
    try:
        return _installed_version("ai-agents-metrics")
    except PackageNotFoundError:
        pass
    try:
        from ai_agents_metrics._version import version
        return version
    except ImportError:
        return "unknown"


__version__ = _resolve_version()
