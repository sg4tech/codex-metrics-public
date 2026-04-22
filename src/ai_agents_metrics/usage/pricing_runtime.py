"""Pricing-file loading and model-alias resolution for token→USD conversion."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ai_agents_metrics.usage.resolution import load_pricing, resolve_pricing_path

if TYPE_CHECKING:
    from pathlib import Path


def resolve_effective_pricing_path(*, cwd: Path, pricing_path: Path | None = None) -> Path:
    """Return the pricing path runtime consumers should use.

    Explicit CLI arguments win. Otherwise fall back to the workspace-aware
    pricing resolution used across the application.
    """
    return pricing_path if pricing_path is not None else resolve_pricing_path(cwd)


def load_effective_pricing(*, cwd: Path, pricing_path: Path | None = None) -> dict[str, dict[str, float | None]]:
    """Load pricing from the effective runtime pricing source."""
    return load_pricing(resolve_effective_pricing_path(cwd=cwd, pricing_path=pricing_path))
