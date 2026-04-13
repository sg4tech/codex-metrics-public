"""Pricing utilities: load model pricing data and compute event costs."""
from __future__ import annotations

import json
import re
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from ai_agents_metrics.domain import parse_iso_datetime_flexible, round_usd

USAGE_FIELD_PATTERNS = {
    "input_tokens": re.compile(r"\binput_token_count=(\d+)"),
    "cached_input_tokens": re.compile(r"\bcached_token_count=(\d+)"),
    "output_tokens": re.compile(r"\boutput_token_count=(\d+)"),
    "reasoning_tokens": re.compile(r"\breasoning_token_count=(\d+)"),
    "tool_tokens": re.compile(r"\btool_token_count=(\d+)"),
    "model": re.compile(r"\bmodel=([^ ]+)"),
    "timestamp": re.compile(r"\bevent\.timestamp=([^ ]+)"),
}
THREAD_MODEL_PATTERN = re.compile(r"\bmodel=([A-Za-z0-9._-]+)")


def default_pricing_path() -> Path:
    return Path(str(resources.files("ai_agents_metrics").joinpath("data/model_pricing.json")))


PRICING_JSON_PATH = default_pricing_path()


def load_pricing(path: Path) -> dict[str, dict[str, float | None]]:
    if not path.exists():
        raise ValueError(f"Pricing file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    models = data.get("models")
    if not isinstance(models, dict):
        raise ValueError(f"Invalid pricing file format: {path}")

    validated_models: dict[str, dict[str, float | None]] = {}
    for model_name, config in models.items():
        if not isinstance(config, dict):
            raise ValueError(f"Invalid pricing config for model: {model_name}")
        required_fields = ("input_per_million_usd", "cached_input_per_million_usd", "output_per_million_usd")
        optional_fields = ("cache_creation_per_million_usd",)
        validated_config: dict[str, float | None] = {}
        for field_name in required_fields:
            if field_name not in config:
                raise ValueError(f"Missing pricing field {field_name} for model: {model_name}")
            value = config[field_name]
            if value is not None and not isinstance(value, (int, float)):
                raise ValueError(f"Invalid pricing value for {model_name}.{field_name}")
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(f"Pricing value cannot be negative for {model_name}.{field_name}")
            validated_config[field_name] = None if value is None else float(value)
        for field_name in optional_fields:
            if field_name in config:
                value = config[field_name]
                if value is not None and not isinstance(value, (int, float)):
                    raise ValueError(f"Invalid pricing value for {model_name}.{field_name}")
                if isinstance(value, (int, float)) and value < 0:
                    raise ValueError(f"Pricing value cannot be negative for {model_name}.{field_name}")
                validated_config[field_name] = None if value is None else float(value)
        validated_models[model_name] = validated_config
    return validated_models


def parse_usage_event(body: str) -> dict[str, Any] | None:
    if 'event.name="codex.sse_event"' not in body or "event.kind=response.completed" not in body:
        return None

    timestamp_match = USAGE_FIELD_PATTERNS["timestamp"].search(body)
    model_match = USAGE_FIELD_PATTERNS["model"].search(body)
    input_match = USAGE_FIELD_PATTERNS["input_tokens"].search(body)
    output_match = USAGE_FIELD_PATTERNS["output_tokens"].search(body)
    cached_match = USAGE_FIELD_PATTERNS["cached_input_tokens"].search(body)
    if timestamp_match is None or model_match is None or input_match is None or output_match is None or cached_match is None:
        return None

    parsed: dict[str, Any] = {
        "timestamp": parse_iso_datetime_flexible(timestamp_match.group(1), "event.timestamp"),
        "model": model_match.group(1),
        "input_tokens": int(input_match.group(1)),
        "cached_input_tokens": int(cached_match.group(1)),
        "output_tokens": int(output_match.group(1)),
    }

    for field_name in ("reasoning_tokens", "tool_tokens"):
        match = USAGE_FIELD_PATTERNS[field_name].search(body)
        parsed[field_name] = int(match.group(1)) if match is not None else 0

    return parsed


def resolve_pricing_model_alias(model: str, pricing: dict[str, dict[str, float | None]]) -> str | None:
    """Resolve a model identifier to its key in the pricing dict, or return None if not found.

    Normalization steps tried in order:
    1. Direct lookup.
    2. Strip trailing date suffix (e.g. claude-sonnet-4-6-20251022 → claude-sonnet-4-6).
    3. OpenAI Codex version suffix (e.g. gpt-5.4 → gpt-5).
    """
    if model in pricing:
        return model

    # Strip trailing date suffix (YYYYMMDD), e.g. claude-sonnet-4-6-20251022 → claude-sonnet-4-6
    date_stripped = re.sub(r"-\d{8}$", "", model)
    if date_stripped != model and date_stripped in pricing:
        return date_stripped

    # OpenAI Codex version suffix alias (e.g. gpt-5.4 → gpt-5)
    if model.endswith(".4"):
        candidate = model.rsplit(".4", maxsplit=1)[0]
        if candidate in pricing:
            return candidate
    if model.endswith(".4-mini"):
        candidate = model.rsplit(".4-mini", maxsplit=1)[0] + "-mini"
        if candidate in pricing:
            return candidate

    return None


def resolve_pricing_path(cwd: Path) -> Path:
    """Return the effective pricing file path for the given workspace.

    If a model_pricing.json exists in the workspace root, it overrides the
    bundled default. Otherwise the bundled package file is used.
    """
    workspace_override = cwd / "model_pricing.json"
    if workspace_override.exists():
        return workspace_override
    return default_pricing_path()


def compute_event_cost_usd(event: dict[str, Any], pricing: dict[str, dict[str, float | None]]) -> float:
    pricing_model = resolve_pricing_model_alias(event["model"], pricing)
    if pricing_model is None:
        return 0.0
    model_pricing = pricing[pricing_model]
    cached_rate = model_pricing["cached_input_per_million_usd"]
    if event["cached_input_tokens"] > 0 and cached_rate is None:
        raise ValueError(f"Model {event['model']} does not support cached input pricing")

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(event["input_tokens"]) / Decimal(1_000_000)
    cached_input_cost = Decimal("0")
    if cached_rate is not None:
        cached_input_cost = Decimal(str(cached_rate)) * Decimal(event["cached_input_tokens"]) / Decimal(1_000_000)
    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(event["output_tokens"]) / Decimal(1_000_000)
    return round_usd(input_cost + cached_input_cost + output_cost)


def compute_claude_event_cost_usd(
    *,
    model: str | None,
    input_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    pricing: dict[str, dict[str, float | None]],
) -> float:
    """Compute cost for a single Claude JSONL assistant event.

    Claude has three distinct token categories:
    - input_tokens: plain (non-cached) input, billed at base input rate
    - cache_creation_input_tokens: tokens written to prompt cache (5-min tier), billed at 1.25× input rate
    - cache_read_input_tokens: tokens read from prompt cache, billed at 0.1× input rate
    - output_tokens: generated output
    """
    if model is None or (input_tokens == 0 and cache_creation_tokens == 0 and cache_read_tokens == 0 and output_tokens == 0):
        return 0.0

    pricing_model = resolve_pricing_model_alias(model, pricing)
    if pricing_model is None:
        return 0.0
    model_pricing = pricing[pricing_model]

    input_cost = Decimal(str(model_pricing["input_per_million_usd"])) * Decimal(input_tokens) / Decimal(1_000_000)

    cache_creation_cost = Decimal("0")
    cache_creation_rate = model_pricing.get("cache_creation_per_million_usd")
    if cache_creation_tokens > 0:
        if cache_creation_rate is None:
            raise ValueError(f"Model {model} does not have cache_creation pricing; cannot price {cache_creation_tokens} cache_creation tokens")
        cache_creation_cost = Decimal(str(cache_creation_rate)) * Decimal(cache_creation_tokens) / Decimal(1_000_000)

    cache_read_cost = Decimal("0")
    cache_read_rate = model_pricing["cached_input_per_million_usd"]
    if cache_read_tokens > 0 and cache_read_rate is not None:
        cache_read_cost = Decimal(str(cache_read_rate)) * Decimal(cache_read_tokens) / Decimal(1_000_000)

    output_cost = Decimal(str(model_pricing["output_per_million_usd"])) * Decimal(output_tokens) / Decimal(1_000_000)

    return round_usd(input_cost + cache_creation_cost + cache_read_cost + output_cost)
