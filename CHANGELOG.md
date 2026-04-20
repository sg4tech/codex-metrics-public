# Changelog

All notable changes to `ai-agents-metrics` will be recorded here.

## Unreleased

## 0.2.0 (2026-04-20)

### Added

- `history-classify` command: new pipeline stage between `history-normalize` and `history-derive` that runs a deterministic classifier over raw session data. Writes structural session-kind labels (main vs subagent) and practice-event rows to the warehouse. Automatically invoked by `history-update` (H-040)
- `derived_practice_events` table: one row per Agent `tool_use` / Skill invocation / slash-command detected in session transcripts, with `practice_name`, `practice_family`, and source coordinates. Enables per-skill analysis of token compression and practice usage patterns (H-040 Phase 2)
- "Findings from real data" section in README linking eight reproducible findings (F-001..F-008) derived from 6 months of Claude Code + Codex history: subagent-aliased retries, `role='user'` pollution, size-confounded practice splits, within-thread compression, per-skill compression ranking
- `docs/warehouse-layering.md`: rules for what each warehouse layer (`raw_*` / `normalized_*` / classified `derived_*` / aggregate `derived_*`) is allowed to contain — source of truth for layer-boundary decisions

### Changed

- `show` history-signals block now reports structural retry pressure (`main_attempt > 1` count) and subagent spawn count instead of the naive file-per-attempt ratio. The old ratio conflated user retries with internal delegation — see F-001
- `render-html`: Chart 3 now stacks by model (one color per model, deterministic palette, unknown pinned last in slate) instead of by input/cached/output tokens — answers "where is my money going?" directly (ARCH-017)
- `render-html`: summary strip gained a "Total Cost" card (sum across all closed goals, success + fail) between Successes and Avg Cost / Success (ARCH-017)

### Fixed

- Project-level token aggregation no longer silently emits zeros when a project has usage events but no derived attempts — `derived_projects` coverage invariant corrected to a one-way relation
- `python -m ai_agents_metrics --version` now displays `python3.X -m ai_agents_metrics <version>` instead of `__main__.py <version>`

### Internal

- `model` column propagated to `derived_session_usage`, `derived_attempts`, and `derived_goals` during derive; unlocks per-model cost analysis without joining back to `normalized_usage_events` (ARCH-016)
- `history/` subpackage gains `classify.py`; `derive.py`, `derive_schema.py`, `derive_insert.py` updated to consume classified inputs

## 0.1.5 (2026-04-13)

### Fixed

- `history-update` and `history-ingest` now default to `--source all`: reads both `~/.codex` and `~/.claude` automatically — Claude Code users no longer need `--source claude` explicitly (CODEX-67)
- `--source all` is now visible in `--help` with per-choice descriptions — was previously an undocumented internal value (CODEX-67)
- `history-update` no longer errors when all sources are absent or skipped — exits cleanly with a summary (CODEX-67)
- `show` now prints an actionable hint when the warehouse does not exist yet: `Run 'ai-agents-metrics history-update' to extract retry pressure and token cost from your agent history files.`
- `show` now prints a Tip when showing all-project fallback: `run history-update from your project directory to get per-project signals.`
- `attempt_count` floor corrected: single-session threads no longer inflate retry counts (CODEX-67)

### Internal

- `history_derive.py` split into a `history/` subpackage (`derive.py`, `derive_build.py`, `derive_insert.py`, `derive_schema.py`) for maintainability (CODEX-68)
- `history_audit.py`, `history_compare.py`, `history_ingest.py`, `history_normalize.py` moved into the `history/` subpackage — import paths unchanged

## 0.1.4 (2026-04-12)

### Fixed

- `show --json` warning now routes to stderr, preventing JSON parse failures in non-git directories (CODEX-62)
- `completion zsh` header corrected from `codex-metrics` to `ai-agents-metrics` — zsh completion now registers under the correct binary name (CODEX-63)
- `history-compare`, `history-normalize`, `history-derive` now include an actionable hint when the warehouse is missing: `Run 'ai-agents-metrics history-update' first.` (CODEX-64)

## 0.1.3 (2026-04-12)

### Fixed

- `show` now falls back to all-project warehouse data when run outside a tracked project directory — Quick Start no longer silently shows zeros
- Warehouse file renamed from `codex_raw_history.sqlite` to `warehouse.db` — matches the path documented in README
- README install section updated: `pipx install` is now the primary recommendation; `pip install` is documented for use inside a virtualenv

## 0.1.2 (2026-04-12)

### New

- `history-update` command: runs the full history pipeline (ingest → normalize → derive) in one step — the primary entry point for history-first users
- `--source claude` support in `history-update` for Claude Code history (`~/.claude`)

### Product

- Repositioned as a history-first tool: point it at existing agent history files and get insights with no manual setup; manual goal tracking (`start-task` / `finish-task`) is now an explicit opt-in enhancement layer
- Policy document (`ai-agents-metrics-policy.md`) updated with Two-Tier Model section to reflect the primary/opt-in split
- Bootstrap policy is now generated from `docs/ai-agents-metrics-policy.md` at build time — single source of truth

### HTML Report

- `render-html` command: self-contained interactive HTML report with four Canvas-rendered trend charts (Successful Tasks, Retry Pressure, Token Cost Breakdown, Cost per Success)
- Warehouse-first reporting: token and retry charts draw from the local SQLite warehouse for full session history; the event log remains the source for goal-type and cost-per-task data
- Report layout split into explicit "Goals Ledger" and "Session History" sections so the two data sources are visible as a feature
- Legend toggle on stacked bar charts: click any legend item to hide/show that series with live Y-axis rescaling

## 0.1.0 (2026-04-08)

First public release.

- CLI for tracking AI-agent goals, attempts, token cost, and retry pressure
- Append-only NDJSON event log as canonical metrics store
- `start-task`, `continue-task`, `finish-task`, `show`, `bootstrap` commands
- Token-based cost calculation with model pricing table
- History pipeline: reconstruct past goals from Codex agent transcripts
- Public boundary guardrails (`make verify-public-boundary`)
- `llms.txt` for AI engine discoverability
