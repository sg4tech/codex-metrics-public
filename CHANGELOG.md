# Changelog

All notable changes to `codex-metrics` will be recorded here.

## 0.1.0 (2026-04-08)

First public release.

- CLI for tracking AI-agent goals, attempts, token cost, and retry pressure
- Append-only NDJSON event log as canonical metrics store
- `start-task`, `continue-task`, `finish-task`, `show`, `bootstrap` commands
- Token-based cost calculation with model pricing table
- History pipeline: reconstruct past goals from Codex agent transcripts
- Public boundary guardrails (`make verify-public-boundary`)
- `llms.txt` for AI engine discoverability
