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
        # Lazy to tolerate editable installs where _version.py is generated on demand.
        from ai_agents_metrics._version import version  # pylint: disable=import-outside-toplevel
        return version
    except ImportError:
        return "unknown"


__version__ = _resolve_version()
