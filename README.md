# codex-metrics

Small Python CLI for tracking Codex goal metrics, attempt history, and usage-derived cost in a repo-friendly format.

This repository is an internal local operator tool. It is meant to help track whether Codex-assisted engineering work is getting better over time, not to act as a public analytics product or hosted service.

## What It Does

`codex-metrics` keeps structured records for:

- goals
- attempts
- success and failure outcomes
- retry pressure
- token and cost signals

The installable CLI lives in the `codex_metrics` package and exposes the `codex-metrics` command.
The repository also keeps `scripts/update_codex_metrics.py` as a compatibility shim for local workflows.

## Main Outputs

The main generated artifacts are:

- `metrics/codex_metrics.json` - source of truth
- `docs/codex-metrics.md` - generated human-readable report

Repository workflow and policy live in:

- `AGENTS.md`
- `docs/codex-metrics-policy.md`

## Quick Start

Requirements:

- Python 3.11+

Install from a checkout:

```bash
python -m pip install .
```

Show CLI help after install:

```bash
codex-metrics --help
```

Repository-local help without installation:

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
codex-metrics init
```

Create or update a goal record:

```bash
codex-metrics update --help
```

Show the current summary:

```bash
codex-metrics show
```

Backfill usage and cost from local Codex logs:

```bash
codex-metrics sync-codex-usage --help
```

Merge a split or superseded goal record:

```bash
codex-metrics merge-tasks --help
```

Typical end-to-end flow:

```bash
codex-metrics init
codex-metrics update --title "Add CSV import" --task-type product --attempts-delta 1
codex-metrics show
```

## Validation Commands

Available `make` targets:

- `make lint`
- `make typecheck`
- `make test`
- `make verify`
- `make coverage`

Build distributable artifacts:

```bash
make package
```

This produces:

- `dist/*.whl`
- `dist/*.tar.gz`

These artifacts are the intended release payload for GitHub Releases and for installing the tool into other projects.

## Release Notes

Recommended release flow:

1. run `make verify`
2. build `wheel` and `sdist` with `make package`
3. smoke-check the built wheel in a clean virtualenv
4. attach the artifacts from `dist/` to a GitHub Release

## Working Notes

- Do not edit generated metrics files manually when the updater can regenerate them.
- Treat `metrics/codex_metrics.json` as the source of truth.
- Goal and attempt bookkeeping is part of the repository workflow, not optional project hygiene.
- Goal-level outcome summary should be read together with entry-level retry history.
