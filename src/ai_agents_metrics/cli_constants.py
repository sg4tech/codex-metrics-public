"""Default paths consumed by the CLI argparse layer and orchestration facade."""
from __future__ import annotations

from pathlib import Path

from ai_agents_metrics.history.ingest import default_raw_warehouse_path

EVENTS_NDJSON_PATH = Path("metrics/events.ndjson")
METRICS_JSON_PATH = EVENTS_NDJSON_PATH  # backward-compat alias used by args.metrics_path
REPORT_MD_PATH = Path("docs/ai-agents-metrics.md")
REPORT_HTML_PATH = Path("reports/report.html")
CODEX_STATE_PATH = Path.home() / ".codex" / "state_5.sqlite"
CODEX_LOGS_PATH = Path.home() / ".codex" / "logs_1.sqlite"
CLAUDE_ROOT = Path.home() / ".claude"
RAW_WAREHOUSE_PATH = default_raw_warehouse_path(METRICS_JSON_PATH)
PUBLIC_BOUNDARY_RULES_PATH = Path("config/public-boundary-rules.toml")
SECURITY_RULES_PATH = Path("config/security-rules.toml")
