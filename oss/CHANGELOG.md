# Changelog

All notable changes to `ai-agents-metrics` will be recorded here.

## Unreleased

- `render-html` command: self-contained interactive HTML report with four Canvas-rendered trend charts (Successful Tasks, Retry Pressure, Token Cost Breakdown, Cost per Success)
- Warehouse-first reporting: token and retry charts draw from the local SQLite warehouse for full session history; the event log remains the source for goal-type and cost-per-task data
- Report layout split into explicit "Goals Ledger" and "Session History" sections so the two data sources are visible as a feature
- Legend toggle on stacked bar charts: click any legend item to hide/show that series with live Y-axis rescaling
- `html_report.py` refactored into four focused modules (`_report_buckets`, `_report_aggregation`, `_report_template`, facade)

## 0.1.0 (2026-04-08)

First public release.

- CLI for tracking AI-agent goals, attempts, token cost, and retry pressure
- Append-only NDJSON event log as canonical metrics store
- `start-task`, `continue-task`, `finish-task`, `show`, `bootstrap` commands
- Token-based cost calculation with model pricing table
- History pipeline: reconstruct past goals from Codex agent transcripts
- Public boundary guardrails (`make verify-public-boundary`)
- `llms.txt` for AI engine discoverability
