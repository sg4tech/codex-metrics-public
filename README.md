# codex-metrics

Small Python CLI for tracking Codex goal metrics, attempt history, and usage-derived cost in a repo-friendly format.

This repository is an internal local operator tool. It is meant to help track whether Codex-assisted engineering work is getting better over time, not to act as a public analytics product or hosted service.

## What It Does

`codex-metrics` keeps structured records for:

- goals
- attempts
- success and failure outcomes
- optional reviewed result fit on product goals
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

Preferred install when a standalone release binary is available:

```bash
# macOS / Linux
chmod +x ./codex-metrics
./codex-metrics --help

# Windows
.\codex-metrics.exe --help
```

Preferred install from source for a standalone CLI:

```bash
pipx install .
```

Fallback install from a checkout:

```bash
# macOS / Linux
python3 -m pip install .

# Windows
py -m pip install .
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

Bootstrap `codex-metrics` into another repository:

```bash
codex-metrics bootstrap
```

Create or update a goal record:

```bash
codex-metrics update --help
```

Show the current summary:

```bash
codex-metrics show
```

Audit stored history for likely misses, partial-fit recoveries, stale in-progress goals, and low cost coverage:

```bash
codex-metrics audit-history
```

Audit why closed product goals are still missing cost coverage:

```bash
codex-metrics audit-cost-coverage
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

## Bootstrap Another Repository

Use this flow when you want to add `codex-metrics` to a different local repository.

Preferred install from a standalone release binary:

```bash
# macOS / Linux
/path/to/codex-metrics bootstrap --dry-run

# Windows
C:\path\to\codex-metrics.exe bootstrap --dry-run
```

Preferred install from source:

```bash
pipx install /Users/viktor/PycharmProjects/codex-metrics
```

Fallback install:

```bash
# macOS / Linux
python3 -m pip install /Users/viktor/PycharmProjects/codex-metrics

# Windows
py -m pip install C:\path\to\codex-metrics
```

Move into the target repository and preview the scaffold:

```bash
cd /path/to/another-repo
codex-metrics bootstrap --dry-run
```

Apply the scaffold:

```bash
codex-metrics bootstrap
```

This creates or updates:

- `metrics/codex_metrics.json`
- `docs/codex-metrics.md`
- `docs/codex-metrics-policy.md`
- `AGENTS.md` with a managed `codex-metrics` block

If the target repo already has a conflicting `docs/codex-metrics-policy.md` and you intentionally want to replace it with the packaged template:

```bash
codex-metrics bootstrap --force
```

First-task flow after bootstrap:

```bash
codex-metrics update --title "My first task" --task-type product --attempts-delta 1
codex-metrics show
codex-metrics update --task-id <goal-id> --status success --notes "Done"
```

## Update In Another Repository

When a new version of `codex-metrics` is released, update the installed package first and then reconcile the scaffold in the target repository.

Update from a local checkout:

```bash
# preferred
pipx install --force /Users/viktor/PycharmProjects/codex-metrics

# macOS / Linux fallback
python3 -m pip install --upgrade /Users/viktor/PycharmProjects/codex-metrics

# Windows fallback
py -m pip install --upgrade C:\path\to\codex-metrics
```

Update from a standalone release binary by replacing the downloaded binary with the newer release artifact, then reconciling the target repository scaffold:

```bash
cd /path/to/another-repo
/path/to/codex-metrics bootstrap --dry-run
/path/to/codex-metrics bootstrap
/path/to/codex-metrics show
```

Update from a built wheel or release artifact:

```bash
# preferred
pipx install --force /path/to/dist/codex_metrics-0.1.0-py3-none-any.whl

# macOS / Linux fallback
python3 -m pip install --upgrade /path/to/dist/codex_metrics-0.1.0-py3-none-any.whl

# Windows fallback
py -m pip install --upgrade C:\path\to\codex_metrics-0.1.0-py3-none-any.whl
```

Then move into the already-bootstrapped target repository and preview what would change:

```bash
cd /path/to/another-repo
codex-metrics bootstrap --dry-run
```

If the preview looks right, apply the update:

```bash
codex-metrics bootstrap
```

Recommended upgrade flow:

1. update the installed package
2. run `codex-metrics bootstrap --dry-run`
3. review any managed-file changes
4. run `codex-metrics bootstrap`
5. run `codex-metrics show`

## Validation Commands

Available `make` targets:

- `make lint`
- `make typecheck`
- `make test`
- `make verify`
- `make live-usage-smoke` for an opt-in end-to-end check against real local Codex telemetry
- `make coverage`

Build distributable artifacts:

```bash
make package
```

This produces:

- `dist/*.whl`
- `dist/*.tar.gz`

These artifacts are the intended release payload for GitHub Releases and for installing the tool into other projects.

Build a standalone binary for the current platform:

```bash
make package-standalone
```

This produces:

- macOS / Linux: `dist/standalone/codex-metrics`
- Windows: `dist/standalone/codex-metrics.exe`

The standalone build is intended for downstream users who should not need `pipx` or direct `pip install` just to run the CLI.

## Release Notes

Recommended release flow:

1. run `make verify`
2. build `wheel` and `sdist` with `make package`
3. build platform-specific standalone artifacts in CI
4. smoke-check both the built wheel and standalone binaries
5. attach the artifacts from `dist/` and standalone CI uploads to a GitHub Release

## Working Notes

- Do not edit generated metrics files manually when the updater can regenerate them.
- Treat `metrics/codex_metrics.json` as the source of truth.
- Goal and attempt bookkeeping is part of the repository workflow, not optional project hygiene.
- Goal-level outcome summary should be read together with entry-level retry history.
