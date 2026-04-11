"""Generate a self-contained HTML report with four trend charts.

Public API (imported by commands.py and tests):
- :func:`aggregate_report_data` — transform raw goals + warehouse rows into chart data
- :func:`render_html_report`    — serialise chart data into a standalone HTML file

All private helpers and the HTML template live in the sub-modules below.
"""
from __future__ import annotations

import json
from typing import Any

from ._report_aggregation import (
    aggregate_report_data,
)
from ._report_template import _HTML_TEMPLATE

__all__ = ["aggregate_report_data", "render_html_report"]


def render_html_report(data: dict[str, Any], generated_at: str) -> str:
    """Return the full HTML string for the report."""
    gran = data.get("granularity", "day")
    gran_noun = "day" if gran == "day" else "week"
    granularity_label = "Daily buckets" if gran == "day" else "Weekly buckets"

    # Escape </script> sequences so JSON cannot break out of the script block.
    safe_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    return (
        _HTML_TEMPLATE
        .replace("{DATA_JSON}", safe_json)
        .replace("{GENERATED_AT}", generated_at)
        .replace("{GRANULARITY_LABEL}", granularity_label)
        .replace("{GRAN_NOUN}", gran_noun)
    )
