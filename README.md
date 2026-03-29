# codex-metrics

Small Python CLI for tracking Codex task metrics, attempt history, and usage-derived cost in a repo-friendly format.

This repository is an internal local operator tool. It is meant to help track whether Codex-assisted engineering work is getting better over time, not to act as a public analytics product or hosted service.

## What It Does

`codex-metrics` keeps structured records for:

- goals
- attempts
- success and failure outcomes
- retry pressure
- token and cost signals

The core CLI lives in `scripts/update_codex_metrics.py`.

## Main Outputs

The main generated artifacts are:

- `metrics/codex_metrics.json` - source of truth
- `docs/codex-metrics.md` - generated human-readable report

Repository workflow and policy live in:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`

## Quick Start

Requirements:

- Python 3.14
- local virtual environment in `.venv`

Show CLI help:

```bash
./.venv/bin/python scripts/update_codex_metrics.py --help
```

Run the standard local verification stack:

```bash
make verify
```

## Main Commands

Initialize metrics files:

```bash
./.venv/bin/python scripts/update_codex_metrics.py init
```

Create or update a task record:

```bash
./.venv/bin/python scripts/update_codex_metrics.py update --help
```

Show the current summary:

```bash
./.venv/bin/python scripts/update_codex_metrics.py show
```

Backfill usage and cost from local Codex logs:

```bash
./.venv/bin/python scripts/update_codex_metrics.py sync-codex-usage --help
```

Merge a split or superseded task record:

```bash
./.venv/bin/python scripts/update_codex_metrics.py merge-tasks --help
```

## Validation Commands

Available `make` targets:

- `make lint`
- `make typecheck`
- `make test`
- `make verify`
- `make coverage`

## Working Notes

- Do not edit generated metrics files manually when the updater can regenerate them.
- Treat `metrics/codex_metrics.json` as the source of truth.
- Goal and attempt bookkeeping is part of the repository workflow, not optional project hygiene.
