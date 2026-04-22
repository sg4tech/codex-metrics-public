"""Generate a self-contained HTML report with four trend charts.

Public API (imported by commands.py and tests):
- :func:`aggregate_report_data` — transform raw goals + warehouse rows into chart data
- :func:`render_html_report`    — serialise chart data into a standalone HTML file
- :func:`check_warehouse_state` — classify the warehouse file for the current project

All private helpers and the HTML template live in the sub-modules below.
"""
from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from ._report_aggregation import (
    aggregate_report_data,
)
from ._report_template import _HTML_TEMPLATE

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["aggregate_report_data", "render_html_report", "check_warehouse_state"]


# Table that is expected in an up-to-date warehouse; used as a proxy for schema
# freshness. If the warehouse predates the practice-events derivation, charts
# that depend on it (chart 5) would silently be empty — we prefer to surface a
# callout pointing to history-update instead.
_SCHEMA_FRESHNESS_TABLE = "derived_practice_events"


def check_warehouse_state(warehouse_path: Path, cwd: str) -> dict[str, str]:
    """Classify the warehouse state for the current project.

    Returns one of four status dicts:
      - ``{"status": "ok"}`` — file exists, schema current, has rows for cwd
      - ``{"status": "missing_file"}`` — warehouse file not present
      - ``{"status": "schema_outdated"}`` — file present but critical table missing
      - ``{"status": "empty_for_cwd"}`` — file and schema fine but 0 rows for cwd

    The HTML template renders a callout for non-ok states with a hint to run
    ``ai-agents-metrics history-update``. This surfaces the silent fallback
    path where warehouse-sourced charts quietly degraded to ledger-only data.
    """
    if not warehouse_path.is_file():
        return {"status": "missing_file"}
    try:
        with sqlite3.connect(warehouse_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "derived_goals" not in tables or _SCHEMA_FRESHNESS_TABLE not in tables:
                return {"status": "schema_outdated"}
            count = conn.execute(
                "SELECT COUNT(*) FROM derived_goals WHERE cwd = ?",
                (cwd,),
            ).fetchone()[0]
            if count == 0:
                return {"status": "empty_for_cwd"}
    except sqlite3.Error:
        # Treat any SQL error (locked, corrupt, schema drift) as needing refresh.
        return {"status": "schema_outdated"}
    return {"status": "ok"}


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
