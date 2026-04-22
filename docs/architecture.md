# Architecture

**What this document is:** A technical map of the codebase — modules, data flow, storage, and integrations.

**When to read this:**
- Getting started as a contributor
- Looking for where a specific feature lives
- Debugging a data or CLI issue and not sure which layer to look at

**Related docs:**
- [decisions.md](decisions.md) — why key architectural choices were made
- [testing-guide.md](testing-guide.md) — how to test each layer
- [data-schema.md](data-schema.md) — what the stored data looks like
- [warehouse-layering.md](warehouse-layering.md) — rules for what each warehouse layer (`raw_*` / `normalized_*` / `derived_*`) is allowed to contain

---

## Summary

`ai-agents-metrics` is a CLI tool for analyzing AI agent work history, tracking spending, and optimizing workflows. It operates as two complementary layers:

**Primary layer — history pipeline:** reads raw session files from `~/.codex` or `~/.claude`, extracts retry pressure, token cost, and session timelines, and stores results in a local SQLite warehouse. No prior instrumentation required.

**Opt-in layer — NDJSON ledger:** an append-only event log for explicit goal boundaries, outcome judgements, and failure reasons. State is reconstructed at read time by replaying events in order.

There is no database server, no background process, and no network dependency.

Data flow:

```
CLI entrypoint (cli.py + cli_parsers.py + cli_constants.py)
  ↓  parses args and dispatches handlers through runtime_facade/
Commands (commands/ package)
  ↓  orchestration against a sanctioned runtime surface (CommandRuntime)
History pipeline (history/*)           ← primary analysis layer
  ↓  ingest → normalize → derive from ~/.codex or ~/.claude
  ↓  SQLite warehouse: retry pressure, token cost, session timeline
Domain (domain/)
  ↓  validates records, serialises/deserialises, computes aggregates
Storage (storage.py)
  ↓  atomic append to metrics/events.ndjson via fcntl lock   ← opt-in ledger
Reporting (reporting.py)
  ↓  computes in-memory summary, merges ledger + warehouse signals
```

---

## How to read this

- **New contributor** → Directory Layout → Entry Points → Data and Storage
- **Working on CLI commands** → Entry Points → Workflow State Machine
- **Working on domain validation or aggregation** → Core Domain
- **Working on storage or event replay** → Data and Storage
- **Working on history reconstruction** → History Pipeline
- **Working on hooks, security, or public boundary** → Integrations

---

## Directory Layout

```
ai-agents-metrics/
├── src/ai_agents_metrics/   # Main Python package
├── tests/               # Pytest test suite
├── scripts/             # Automation and utility scripts
├── tools/               # CLI wrapper (tools/ai-agents-metrics)
├── config/              # Public boundary rules (TOML)
├── metrics/             # Generated output: events.ndjson + lockfile
├── pricing/             # Token pricing data
├── .githooks/           # commit-msg, pre-commit, pre-push hooks
└── pyproject.toml       # Package config, ruff, mypy, pytest settings
```

---

## Package: `src/ai_agents_metrics/`

### Entry Points

| File / Package | Role |
|----------------|------|
| `__init__.py` | Version resolution: git-derived (`commit_count.sha`) with fallback to package metadata |
| `__main__.py` | Enables `python -m ai_agents_metrics` dispatch |
| `cli.py` | CLI dispatcher + facade surface for `scripts/metrics_cli.py` — records invocation, routes `args.command` to handlers, exposes `console_main` |
| `cli_parsers.py` | Argparse parser construction (`build_parser`, per-group `_add_*_parsers` helpers, hidden-command filter) |
| `cli_constants.py` | Path defaults (`METRICS_JSON_PATH`, `CODEX_STATE_PATH`, `CLAUDE_ROOT`, `RAW_WAREHOUSE_PATH`, …) consumed by both `cli.py` and `cli_parsers.py` |
| `commands/` | Package of CLI command handlers split by cluster: `install`, `history`, `tasks`, `report`, `misc`; `_runtime.py` defines the `CommandRuntime` Protocol; `__init__.py` re-exports every `handle_*` for backward-compatible `from ai_agents_metrics import commands` |
| `runtime_facade/` | Concrete `CommandRuntime` implementation split into three submodules: `orchestration` (path constants, history wrappers, workflow helpers, init/bootstrap), `costs` (usage-cost resolution, `resolve_goal_usage_updates`, cost-audit), `mutations` (`upsert_task`, `sync_usage`, `merge_tasks`); `__init__.py` re-exports the full `__all__` surface |

### Core Domain

| File | Role |
|------|------|
| `domain/` | Domain package split into submodules: `models.py` (dataclasses), `serde.py` (from_dict / to_dict — the only place that converts timestamps between `str` and `datetime`), `validation.py`, `aggregation.py`, `ids.py`, `time_utils.py`. Public API re-exported via `domain/__init__.py`. |
| `storage.py` | Atomic file writes and fcntl lockfile helpers |
| `workflow_fsm.py` | Task lifecycle state machine (see below) |

### History Pipeline

Sequential stages that reconstruct goal history from raw Codex + Claude Code agent state:

```
Codex (~/.codex) or Claude Code (~/.claude)
  ↓  history/ingest/         → .ai-agents-metrics/warehouse.db (raw_* tables)
       ingest/warehouse.py     — schema, SQL helpers, manifest, path resolution
       ingest/codex.py         — Codex adapter (state_5.sqlite, logs_1.sqlite, session JSONL)
       ingest/claude.py        — Claude Code adapter (projects/*.jsonl, subagent files)
       ingest/__init__.py      — orchestrator (ingest_codex_history), IngestSummary, snapshots
  ↓  history/normalize.py    → cleaned warehouse rows (normalized_* tables)
  ↓  history/classify.py     → session kinds (main vs subagent) + practice-event labels
  ↓  history/derive.py       → GoalRecord + AttemptEntryRecord objects (derived_* tables)
       history/derive_build.py    — pipeline stage builders
       history/derive_insert.py   — typed inserts into derived_*
       history/derive_schema.py   — schema for derived tables
  ↓  history/compare.py      → diff against replayed metrics state
       history/compare_store.py  (persistence for compare results)
       history/audit.py          (consistency checks on derived goals)
```

For the layering rules (raw_* byte-perfect, normalized_* typed, derived_* aggregated) see
`warehouse-layering.md`.

### Analysis and Reporting

| File | Role |
|------|------|
| `reporting.py` | Markdown generation, product quality summaries, agent recommendations |
| `cost_audit.py` | Audits missing/incomplete token and cost data; categorises issues |
| `retro_timeline.py` | Derives a retrospective work timeline from goal records |
| `html_report.py` | Public facade for the HTML report: re-exports `aggregate_report_data` and `render_html_report` |
| `_report_aggregation.py` | Transforms ndjson goals + warehouse rows into chart-ready series; `_apply_token_pricing` applies model-aware pricing |
| `_report_buckets.py` | Pure date/time-bucket helpers (parse, bucket key, make buckets) |
| `_report_template.py` | Self-contained HTML/CSS/JS template string; no Python logic |

### Integrations

| File | Role |
|------|------|
| `pricing_runtime.py` | Sanctioned application-level pricing API: resolves effective pricing path and loads workspace-aware pricing |
| `usage_resolution.py` | Pricing data loading, usage event parsing, cost computation, and window resolution logic for Claude and Codex sessions |
| `usage_backends.py` | `UsageBackend` Protocol with `ClaudeUsageBackend` and `UnknownUsageBackend` implementations; delegates window resolution to `usage_resolution` |
| `git_hooks.py` | Implements commit-msg validation and pre-push security scanning logic |
| `commit_message.py` | Validates commit subject format (`CODEX-123:` / `NO-TASK:`) |
| `public_boundary.py` | Verifies files against TOML-configured inclusion/exclusion rules |
| `observability.py` | Appends mutation events to `.ai-agents-metrics/events.sqlite` and a debug log |
| `bootstrap.py` | Project initialisation — scaffold, preflight checks, safe reruns |
| `completion.py` | Shell tab-completion helpers |

---

## Workflow State Machine (`workflow_fsm.py`)

States and events that gate CLI command behaviour:

**States:**
- `CLEAN_NO_ACTIVE_GOAL` — repo has no active goal, no uncommitted work
- `ACTIVE_GOAL_EXISTS` — exactly one in-progress goal is open
- `STARTED_WORK_WITHOUT_ACTIVE_GOAL` — uncommitted changes detected, no goal open
- `CLOSED_GOAL_REPAIR` — most recent goal is closed; repair path available
- `DETECTION_UNCERTAIN` — git unavailable or state ambiguous

**Events:** `start-task`, `continue-task`, `finish-task(success/fail)`, `update(create/close/repair)`, `ensure-active-task`, `show`

Transitions produce a `WorkflowDecision(action, message)`. Commands call `classify_workflow_state()` then `resolve_workflow_decision()` to determine whether to proceed, block, or prompt repair.

---

## Data and Storage

**Primary store:** `metrics/events.ndjson`
- Append-only NDJSON event log; one JSON line per CLI command
- Event types: `goal_started`, `goal_continued`, `goal_finished`, `goal_updated`, `goals_merged`, `usage_synced`
- State reconstructed at read time via last-write-wins replay per `goal_id` / `entry_id`
- Summary is always computed in-memory from the replayed state; it is never persisted
- Mutations serialised via fcntl lockfile (`metrics/events.ndjson.lock`)

**History warehouse:** `.ai-agents-metrics/warehouse.db`
- Intermediate cache populated by `history/ingest/` (Codex + Claude adapters)
- Consumed by normalize → classify → derive steps; not the source of truth
- Also read directly by `render-html` for token/cost and retry data (warehouse-first reporting, H-038): covers full session history, while the ndjson ledger only covers manually-tracked goals

**Event log:** `.ai-agents-metrics/events.sqlite` + `events.debug.log`
- Append-only mutation audit trail written by `observability.py`

---

## CLI Entry Points

**Installed command:** `ai-agents-metrics` → `ai_agents_metrics.cli:console_main`
**Repo wrapper:** `tools/ai-agents-metrics` — thin shell script, no pip install required

Boundary note:

- `cli.py` is the entrypoint module, not the general runtime dependency surface
- `commands/` depends on `runtime_facade/`, not on `cli.py` (enforced by import-linter)
- Inside `runtime_facade/` the one-way direction is `mutations → costs → orchestration`
- pricing-aware runtime consumers should go through `pricing_runtime.py`, not ad-hoc pricing-path resolution

Key command groups:

| Group | Commands |
|-------|----------|
| Task lifecycle | `start-task`, `continue-task`, `finish-task` |
| Metrics mutation | `update`, `merge-tasks`, `ensure-active-task` |
| Inspection | `show`, `render-report`, `render-html` |
| History pipeline | `history-ingest`, `history-normalize`, `history-classify`, `history-derive`, `history-update` |
| History audit | `history-compare`, `history-audit`, `audit-cost-coverage`, `derive-retro-timeline` |
| Sync | `sync-usage`, `sync-codex-usage` |
| Tooling | `init`, `bootstrap`, `install-self`, `completion`, `verify-public-boundary`, `security` |

---

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `metrics_cli.py` | CLI entry point shim for local development |
| `public_overlay.py` | Bidirectional sync between private repo and `oss/` public mirror |
| `build_standalone.py` | Builds self-contained binary distribution |
| `check_live_usage_recovery.py` | Smoke test for live usage data recovery |

---

## Tests (`tests/`)

One test file per module; naming mirrors the source:

| Test file | Covers |
|-----------|--------|
| `test_metrics_cli.py` | Full CLI workflow integration |
| `test_metrics_domain.py` | Domain model logic |
| `test_workflow_fsm.py` | State machine transitions |
| `test_history_{ingest,normalize,derive,compare,audit}.py` | Pipeline stages |
| `test_storage_roundtrip.py` | Event log I/O and replay |
| `test_{cost_audit,reporting,retro_timeline}.py` | Analysis and reporting |
| `test_{git_hooks,commit_message,public_boundary}.py` | Integrations |
| `test_observability.py` | Event recording |
| `test_public_overlay.py` | Public/private sync |
| `test_claude_md.py` | Documentation generation |

`conftest.py` provides shared fixtures (temp metrics paths, fake goal factories, etc.).

---

## Code Quality Configuration

| Tool | Config | Settings |
|------|--------|----------|
| **ruff** | `pyproject.toml` | 15 rule categories (B, C4, ERA, F, FURB, I, PERF, PGH, PTH, Q, RET, RSE, SIM, TC, UP); target Python 3.14; line length 100 |
| **mypy** | `pyproject.toml` | `strict = true` at top level (ARCH-030); covers `src/` + `scripts/`; 65/65 files pass `--strict` |
| **import-linter** | `pyproject.toml` | Six architectural contracts: domain/storage/history boundaries, usage-layer restrictions, package modules must not import `cli.py` outside the entrypoint shim |
| **pylint** | `pyproject.toml` + `Makefile` | Full default rule set on the whole project (ARCH-019 … ARCH-023); a small `disable` list documents the few intentionally-off rules |
| **hypothesis** | `pyproject.toml` dev dep | Property-based tests for `domain/aggregation` (8 invariants) and `history/normalize` (8 invariants); strategies in `tests/strategies/` |
| **pytest** | `pyproject.toml` | `pythonpath = ["src"]`, xdist auto workers, 5s default timeout (overridden per-test on hypothesis suites) |
| **coverage** | `pyproject.toml` | Branch coverage, parallel mode, source = `ai_agents_metrics` |

**Makefile targets:** `lint`, `security`, `typecheck`, `test`, `arch-check`, `verify`, `verify-fast`, `coverage`, `package`, public-overlay ops.

**Git hooks (`.githooks/`):**
- `commit-msg` — rejects commits not matching `CODEX-NNN:` or `NO-TASK:` prefix
- `pre-commit` — runs ruff on staged Python files
- `pre-push` — runs `make verify` when Python files are in the push
