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

---

## Summary

`ai-agents-metrics` is a CLI tool that appends events to a local NDJSON log. State is reconstructed at read time by replaying events in order. There is no database server, no background process, and no network dependency.

Data flow:

```
CLI (cli.py)
  ↓  parses args, validates workflow state via workflow_fsm.py
Domain (domain/)
  ↓  validates records, serialises/deserialises, computes aggregates
Storage (storage.py)
  ↓  atomic append to metrics/events.ndjson via fcntl lock
Reporting (reporting.py)
  ↓  computes in-memory summary, generates markdown
History pipeline (history_*.py)
  ↓  optional: reconstructs past goals from raw agent transcripts
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

| File | Role |
|------|------|
| `__init__.py` | Version resolution: git-derived (`commit_count.sha`) with fallback to package metadata |
| `__main__.py` | Enables `python -m ai_agents_metrics` dispatch |
| `cli.py` | Main CLI — argparse, all subcommands, `console_main` entrypoint |

### Core Domain

| File | Role |
|------|------|
| `domain/` | Domain package split into submodules: `models.py` (dataclasses), `serde.py` (from_dict / to_dict — the only place that converts timestamps between `str` and `datetime`), `validation.py`, `aggregation.py`, `ids.py`, `time_utils.py`. Public API re-exported via `domain/__init__.py`. |
| `storage.py` | Atomic file writes and fcntl lockfile helpers |
| `commands.py` | `CommandRuntime` Protocol — dependency injection interface for CLI commands |
| `workflow_fsm.py` | Task lifecycle state machine (see below) |

### History Pipeline

Four sequential modules that reconstruct goal history from raw Codex agent state:

```
Codex state/logs (SQLite)
  ↓  history_ingest.py       → .ai-agents-metrics/codex_raw_history.sqlite
  ↓  history_normalize.py    → cleaned warehouse rows
  ↓  history_derive.py       → GoalRecord + AttemptEntryRecord objects
  ↓  history_compare.py      → diff against replayed metrics state
       history_compare_store.py  (persistence for compare results)
       history_audit.py          (consistency checks on derived goals)
```

### Analysis and Reporting

| File | Role |
|------|------|
| `reporting.py` | Markdown generation, product quality summaries, agent recommendations |
| `cost_audit.py` | Audits missing/incomplete token and cost data; categorises issues |
| `retro_timeline.py` | Derives a retrospective work timeline from goal records |

### Integrations

| File | Role |
|------|------|
| `usage_backends.py` | `UsageBackend` Protocol with `ClaudeUsageBackend` and `UnknownUsageBackend` implementations; resolves token/cost windows |
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

**History warehouse:** `.ai-agents-metrics/codex_raw_history.sqlite`
- Intermediate cache populated by `history_ingest.py`
- Consumed by normalize → derive steps; not the source of truth

**Event log:** `.ai-agents-metrics/events.sqlite` + `events.debug.log`
- Append-only mutation audit trail written by `observability.py`

---

## CLI Entry Points

**Installed command:** `ai-agents-metrics` → `ai_agents_metrics.cli:console_main`
**Repo wrapper:** `tools/ai-agents-metrics` — thin shell script, no pip install required

Key command groups:

| Group | Commands |
|-------|----------|
| Task lifecycle | `start-task`, `continue-task`, `finish-task` |
| Metrics mutation | `update`, `create`, `merge-tasks` |
| Inspection | `show`, `show-goal`, `render-report` |
| History | `history-ingest`, `history-normalize`, `history-derive`, `history-compare`, `history-audit` |
| Sync | `sync-usage` |
| Tooling | `init`, `verify-public-boundary`, `render-completion`, `export` |

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
| **ruff** | `pyproject.toml` | Rules: F (pyflakes) + I (isort); target Python 3.14; line length 100 |
| **mypy** | `pyproject.toml` | Strict: `check_untyped_defs`, `disallow_incomplete_defs`, `no_implicit_optional`; covers `src/` + `scripts/metrics_cli.py` |
| **pytest** | `pyproject.toml` | `pythonpath = ["src"]` |
| **coverage** | `pyproject.toml` | Branch coverage, parallel mode, source = `ai_agents_metrics` |

**Makefile targets:** `lint`, `security`, `typecheck`, `test`, `verify` (all four in sequence), `coverage`, `package`, public-overlay ops.

**Git hooks (`.githooks/`):**
- `commit-msg` — rejects commits not matching `CODEX-NNN:` or `NO-TASK:` prefix
- `pre-commit` — runs ruff on staged Python files
- `pre-push` — runs `make verify` when Python files are in the push
