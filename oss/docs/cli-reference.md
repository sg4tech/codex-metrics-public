# CLI Reference

`ai-agents-metrics` is a local CLI for analyzing your AI agent work history, tracking spending, and optimizing how you work. The primary flow reads your existing conversation history files — no manual setup required to get value.

All commands are invoked via `ai-agents-metrics <command> [flags]`.

---

## Naming note

Command names and flags use `task` (`start-task`, `--task-id`, `--task-type`, etc.). This is intentional — `task` is the CLI-level term for the unit of work being tracked. Treat it as equivalent to "goal" when reading other documentation.

---

## Typical workflow

### Primary flow — history extraction (no prior setup required)

```bash
# Ingest your agent session history into a local warehouse
ai-agents-metrics history-ingest                   # Codex (~/.codex)
ai-agents-metrics history-ingest --source claude   # Claude Code (~/.claude)

# Build normalized and derived analysis layers
ai-agents-metrics history-normalize
ai-agents-metrics history-derive

# Inspect: retry pressure, token cost, session timeline
ai-agents-metrics show
```

### Opt-in enhancement — manual goal tracking

For explicit goal boundaries, outcome judgements (`result-fit`), and classified failure reasons:

```bash
# One-time setup: scaffold the ledger into a repository
ai-agents-metrics bootstrap --target-dir /path/to/repo

# Open a goal before starting work
ai-agents-metrics start-task --title "Add typed pipeline contracts" --task-type product

# Record another pass if needed
ai-agents-metrics continue-task --task-id 2026-04-08-001 --failure-reason validation_failed

# Close the goal
ai-agents-metrics finish-task --task-id 2026-04-08-001 --status success --result-fit exact_fit

# show combines ledger + history warehouse into a unified view
ai-agents-metrics show
```

---

## Common flags

Most commands accept these flags. Defaults are set for the current repository.

| Flag | Default | Meaning |
|------|---------|---------|
| `--metrics-path` | `metrics/events.ndjson` | Append-only event log |
| `--report-path` | `docs/ai-agents-metrics.md` | Optional markdown export |
| `--write-report` | off | Also regenerate the markdown report |

---

## Core commands

The primary workflow for tracking AI-assisted engineering work.

### `start-task`

Create a new goal and record the first implementation pass.

| Flag | Required | Description |
|------|----------|-------------|
| `--title` | yes | Goal title |
| `--task-type` | yes | `product`, `meta`, or `retro` |
| `--notes` | no | Note recorded on the goal and first attempt |
| `--continuation-of` | no | Link to a previous closed goal (mutually exclusive with `--supersedes-task-id`) |
| `--supersedes-task-id` | no | Replace a previous closed goal |
| `--started-at` | no | Explicit ISO8601 start timestamp |
| `--cost-usd-add` | no | Add explicit USD cost for this pass |
| `--model` / `--input-tokens` / `--output-tokens` | no | Token-based cost calculation |

```bash
ai-agents-metrics start-task --title "Add typed pipeline contracts" --task-type product
ai-agents-metrics start-task --title "Write weekly retro" --task-type retro
```

### `continue-task`

Record another implementation pass for an existing in-progress goal.

| Flag | Required | Description |
|------|----------|-------------|
| `--task-id` | yes | Existing goal identifier |
| `--notes` | no | Note for the new attempt |
| `--failure-reason` | no | Failure reason for this pass if it was unsuccessful |
| `--started-at` | no | Explicit ISO8601 timestamp for the new pass |
| `--cost-usd-add` | no | Cost for this pass |

```bash
ai-agents-metrics continue-task --task-id 2026-04-08-001 --failure-reason validation_failed
```

### `finish-task`

Close an existing goal as success or fail.

| Flag | Required | Description |
|------|----------|-------------|
| `--task-id` | yes | Existing goal identifier |
| `--status` | yes | `success` or `fail` |
| `--failure-reason` | no | Required when `--status fail` |
| `--result-fit` | no | Quality judgement for product goals: `exact_fit`, `partial_fit`, `miss` |
| `--notes` | no | Final note |
| `--finished-at` | no | Explicit ISO8601 finish timestamp |
| `--cost-usd-add` | no | Cost for the final pass |

```bash
ai-agents-metrics finish-task --task-id 2026-04-08-001 --status success
ai-agents-metrics finish-task --task-id 2026-04-08-001 --status fail --failure-reason unclear_task
```

---

## Inspection

Read-only commands for querying and reviewing stored metrics.

### `show`

Print the current summary, cost coverage, and operator review. Use this for a quick status check.

```bash
ai-agents-metrics show
```

### `history-audit`

Analyze stored goal history and print audit candidates: likely misses, partial-fit recoveries, stale in-progress goals, and low-cost-coverage product goals.

```bash
ai-agents-metrics history-audit
```

### `audit-cost-coverage`

Inspect closed product goals and explain why cost coverage is missing, partial, or potentially recoverable from local agent logs.

| Flag | Default | Description |
|------|---------|-------------|
| `--pricing-path` | `config/pricing.json` | Pricing model definitions |
| `--codex-state-path` | agent state path | Local agent state file |

```bash
ai-agents-metrics audit-cost-coverage
```

### `history-compare`

Compare the structured metrics ledger against reconstructed agent session history in the SQLite warehouse. Useful for catching gaps between recorded goals and actual agent sessions.

| Flag | Default | Description |
|------|---------|-------------|
| `--warehouse-path` | `.ai-agents-metrics/warehouse.db` | SQLite warehouse |
| `--cwd` | current directory | Repository root to filter by |

```bash
ai-agents-metrics history-compare
```

### `render-report`

Regenerate the optional `docs/ai-agents-metrics.md` markdown export from the NDJSON event log. Does not mutate events.

```bash
ai-agents-metrics render-report
```

---

## Setup

Commands for bootstrapping metrics into a repository and managing the local installation.

### `bootstrap`

Scaffold the full ai-agents-metrics setup into a repository: creates the metrics artifact, `docs/ai-agents-metrics-policy.md`, and a managed policy block inside the agent instructions file. Safe to rerun on a partial scaffold.

| Flag | Default | Description |
|------|---------|-------------|
| `--target-dir` | `.` | Repository root to initialize |
| `--agents-path` | `AGENTS.md` | Instructions file to inject the policy block into |
| `--policy-path` | `docs/ai-agents-metrics-policy.md` | Policy file destination |
| `--command-path` | `tools/ai-agents-metrics` | Executable wrapper destination |
| `--force` | off | Replace conflicting scaffold files |
| `--dry-run` | off | Preview planned changes without writing |

```bash
ai-agents-metrics bootstrap --target-dir /path/to/repo --dry-run
ai-agents-metrics bootstrap --target-dir /path/to/repo
```

### `init`

Create the metrics NDJSON event log. Use this to initialize storage in a repository that already has other scaffold files in place.

| Flag | Default | Description |
|------|---------|-------------|
| `--force` | off | Overwrite existing metrics files |
| `--write-report` | off | Also render the markdown export |

```bash
ai-agents-metrics init
ai-agents-metrics init --force --write-report
```

### `install-self`

Install the current ai-agents-metrics executable into a stable user-local location (default: `~/bin/ai-agents-metrics` symlink).

| Flag | Default | Description |
|------|---------|-------------|
| `--target-dir` | `~/bin` | Installation directory |
| `--copy` | off | Copy instead of symlink |
| `--write-shell-profile` | off | Append target dir to shell profile if not on PATH |

```bash
ai-agents-metrics install-self
ai-agents-metrics install-self --copy
```

### `completion`

Print a shell completion script for `bash` or `zsh`.

```bash
ai-agents-metrics completion zsh >> ~/.zshrc
ai-agents-metrics completion bash >> ~/.bashrc
```

### `ensure-active-task`

Inspect the current git working tree for meaningful repository work and ensure that active task bookkeeping exists. If work has started without an active goal, creates a recovery draft.

```bash
ai-agents-metrics ensure-active-task
```

---

## Record repair

Low-level commands for direct record manipulation and history correction. Use these for one-off fixes and history replay, not normal tracking.

### `update`

Create a new goal or update an existing one. More flexible than the lifecycle commands; primarily useful for history replay and corrections.

Key flags: `--task-id`, `--title`, `--task-type`, `--status`, `--attempts-delta`, `--attempts`, `--cost-usd-add`, `--cost-usd`, `--tokens-add`, `--tokens`, `--failure-reason`, `--result-fit`, `--notes`, `--started-at`, `--finished-at`, `--continuation-of`, `--supersedes-task-id`.

```bash
# New goal
ai-agents-metrics update --title "Improve CLI help" --task-type product --attempts-delta 1
# Update existing
ai-agents-metrics update --task-id 2026-03-29-010 --status success --notes "Validated"
```

### `merge-tasks`

Recombine a mistakenly split goal into one kept goal. Transfers attempt history from the dropped goal.

| Flag | Required | Description |
|------|----------|-------------|
| `--keep-task-id` | yes | Goal that should remain after the merge |
| `--drop-task-id` | yes | Goal that should be merged in and removed |

```bash
ai-agents-metrics merge-tasks --keep-task-id 2026-04-01-001 --drop-task-id 2026-04-01-002
```

---

## Cost sync

### `sync-usage`

Backfill known cost and token totals from local agent telemetry into existing in-progress goal records. Reads agent state and log files to recover usage data without requiring manual input.

| Flag | Default | Description |
|------|---------|-------------|
| `--pricing-path` | `config/pricing.json` | Pricing model definitions |
| `--usage-state-path` | agent state path | Local agent state file |
| `--usage-logs-path` | agent logs path | Local agent log directory |
| `--usage-thread-id` | none | Specific thread to backfill from |
| `--claude-root` | `~/.claude` | Claude agent root directory |

```bash
ai-agents-metrics sync-usage
```

> **Note:** `sync-codex-usage` is a deprecated alias for `sync-usage`.

---

## History pipeline

Sequential pipeline for ingesting and analyzing raw agent session history. Run in order: ingest → normalize → derive.

Supports two agent sources via `--source`:
- `codex` (default): reads from `~/.codex`
- `claude`: reads from `~/.claude/projects/` (Claude Code full transcript + tokens)

### `history-ingest`

Read thread metadata, session transcripts, telemetry events, and logs from a local agent history directory into a raw SQLite warehouse.

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | `codex` | Agent source: `codex` or `claude` |
| `--source-root` | `~/.codex` / `~/.claude` | Override agent history root |
| `--warehouse-path` | `.ai-agents-metrics/warehouse.db` | Output SQLite warehouse |

```bash
ai-agents-metrics history-ingest
ai-agents-metrics history-ingest --source claude
```

### `history-normalize`

Read the raw warehouse and build normalized summary tables for downstream analysis.

| Flag | Default | Description |
|------|---------|-------------|
| `--warehouse-path` | `.ai-agents-metrics/warehouse.db` | Warehouse with raw data |

```bash
ai-agents-metrics history-normalize
```

### `history-derive`

Read the normalized warehouse and build reusable analysis marts: goals, attempts, timelines, retry chains, and session usage.

| Flag | Default | Description |
|------|---------|-------------|
| `--warehouse-path` | `.ai-agents-metrics/warehouse.db` | Warehouse with normalized data |

```bash
ai-agents-metrics history-derive
```

### `derive-retro-timeline`

Build a retrospective timeline dataset and print before/after product-metric windows around each retrospective event.

| Flag | Default | Description |
|------|---------|-------------|
| `--warehouse-path` | `.ai-agents-metrics/warehouse.db` | Warehouse with normalized data |
| `--cwd` | current directory | Repository root to filter by |
| `--window-size` | `5` | Number of goals before/after each retro |

```bash
ai-agents-metrics derive-retro-timeline
```

---

## Security

### `verify-public-boundary`

Check a candidate public repository tree against explicit boundary rules. Fails on forbidden paths, forbidden file types, unexpected roots, or private-content markers.

| Flag | Default | Description |
|------|---------|-------------|
| `--repo-root` | `.` | Repository root to check |
| `--rules-path` | `config/public-boundary-rules.json` | Boundary rules file |

```bash
ai-agents-metrics verify-public-boundary --repo-root /path/to/public-clone
```

### `security`

Scan staged changes for secrets, token patterns, private keys, and other dangerous data before it lands in git. Typically invoked from a pre-commit hook.

| Flag | Default | Description |
|------|---------|-------------|
| `--repo-root` | `.` | Repository root |
| `--rules-path` | `config/security-rules.json` | Security rules file |

```bash
ai-agents-metrics security
```
