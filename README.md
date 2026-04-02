# codex-metrics

Small Python CLI for tracking AI-agent goal metrics, attempt history, and usage-derived cost in a repo-friendly format.

This repository is an internal local operator tool. It is meant to help track whether AI-agent-assisted engineering work is getting better over time, not to act as a public analytics product or hosted service.

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
- `docs/codex-metrics.md` - optional markdown export rendered on demand

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

When you use the standalone binary directly, `codex-metrics` does not automatically appear in your shell `PATH`.
Run it by path, for example `./codex-metrics ...` or `/path/to/codex-metrics ...`, unless you move it into a directory that is already on `PATH`.

Recommended self-host install on macOS/Linux:

```bash
/absolute/path/to/codex-metrics install-self
codex-metrics --help
```

This keeps one stable command on `PATH` and avoids copying a separate binary into each repository.
If `~/bin` is not yet on `PATH`, `install-self` will print the exact `export PATH=...` line to add to your shell profile.
If you want the installer to append that line automatically for your detected shell:

```bash
/absolute/path/to/codex-metrics install-self --write-shell-profile
exec $SHELL -l
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

Render the optional markdown report:

```bash
codex-metrics render-report
```

Bootstrap `codex-metrics` into another repository:

```bash
codex-metrics bootstrap
```

Install the current executable into `~/bin/codex-metrics`:

```bash
/path/to/codex-metrics install-self
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

Ingest local `~/.codex` history into a raw SQLite warehouse:

```bash
codex-metrics ingest-codex-history --help
```

Normalize the raw warehouse into analysis-friendly tables:

```bash
codex-metrics normalize-codex-history --help
```

Audit why closed product goals are still missing cost coverage:

```bash
codex-metrics audit-cost-coverage
```

Backfill usage and cost from local agent logs:

```bash
codex-metrics sync-usage --help
```

`sync-codex-usage` remains available as a compatibility alias.

Merge a split or superseded goal record:

```bash
codex-metrics merge-tasks --help
```

Print shell completion for `bash` or `zsh`:

```bash
codex-metrics completion zsh
```

Typical end-to-end flow:

```bash
codex-metrics init
codex-metrics start-task --title "Add CSV import" --task-type product
codex-metrics continue-task --task-id <goal-id> --notes "Retry after review"
codex-metrics finish-task --task-id <goal-id> --status success --notes "Validated"
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

Recommended self-host setup on macOS/Linux before bootstrapping repositories:

```bash
/absolute/path/to/codex-metrics install-self
codex-metrics --help
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
/path/to/codex-metrics bootstrap --dry-run
```

Apply the scaffold:

```bash
/path/to/codex-metrics bootstrap
```

This creates or updates:

- `metrics/codex_metrics.json`
- `docs/codex-metrics-policy.md`
- `tools/codex-metrics` repo-local wrapper
- `AGENTS.md` with a managed `codex-metrics` block

If you also want the optional markdown export during bootstrap:

```bash
/path/to/codex-metrics bootstrap --write-report
```

If the target repo already has a conflicting `docs/codex-metrics-policy.md` and you intentionally want to replace it with the packaged template:

```bash
/path/to/codex-metrics bootstrap --force
```

First-task flow after bootstrap:

```bash
./tools/codex-metrics start-task --title "My first task" --task-type product
./tools/codex-metrics show
./tools/codex-metrics finish-task --task-id <goal-id> --status success --notes "Done"
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

For active development in this repository, prefer an editable local install so the source tree, `python -m codex_metrics`, and `./.venv/bin/codex-metrics` stay in sync:

```bash
make dev-refresh-local
./.venv/bin/codex-metrics --version
./.venv/bin/python -m codex_metrics --version
```

Use `make package-refresh-local` only when you intentionally want to verify the built wheel surface, not as the default inner-loop development refresh.

Update from a standalone release binary by replacing the downloaded binary with the newer release artifact, then reconciling the target repository scaffold:

```bash
cd /path/to/another-repo
/path/to/codex-metrics bootstrap --dry-run
/path/to/codex-metrics bootstrap
/path/to/codex-metrics show
```

Recommended self-host update on macOS/Linux when you keep a stable symlink in `~/bin`:

```bash
/path/to/new/codex-metrics install-self

cd /path/to/another-repo
codex-metrics bootstrap --dry-run
codex-metrics bootstrap
codex-metrics show
```

Update from a built wheel or release artifact:

```bash
# preferred
pipx install --force /path/to/dist/codex_metrics-<version>-py3-none-any.whl

# macOS / Linux fallback
python3 -m pip install --upgrade /path/to/dist/codex_metrics-<version>-py3-none-any.whl

# Windows fallback
py -m pip install --upgrade C:\path\to\codex_metrics-<version>-py3-none-any.whl
```

Then move into the already-bootstrapped target repository and preview what would change:

```bash
cd /path/to/another-repo
/path/to/codex-metrics bootstrap --dry-run
```

If the preview looks right, apply the update:

```bash
/path/to/codex-metrics bootstrap
```

Recommended upgrade flow:

1. update the installed package
2. run `codex-metrics bootstrap --dry-run`
3. review any managed-file changes
4. run `codex-metrics bootstrap`
5. run `codex-metrics show`

## Troubleshooting

If you see `zsh: command not found: codex-metrics` after downloading a standalone binary, that usually means the binary is not installed on your shell `PATH`.

Use one of these forms instead:

```bash
./codex-metrics --help
/path/to/codex-metrics bootstrap
```

Or move the binary into a directory on `PATH`, for example `~/bin` or `/usr/local/bin`, and then reopen your shell.
For repeated self-host use on macOS/Linux, prefer a stable symlink at `~/bin/codex-metrics`.

The fastest way to create that symlink is:

```bash
/path/to/codex-metrics install-self
```

To enable shell completion after `codex-metrics` is on `PATH`:

```bash
# zsh
mkdir -p ~/.zfunc
codex-metrics completion zsh > ~/.zfunc/_codex-metrics
echo 'fpath=(~/.zfunc $fpath)' >> ~/.zshrc
echo 'autoload -Uz compinit && compinit' >> ~/.zshrc
exec $SHELL -l
```

```bash
# bash
mkdir -p ~/.local/share/bash-completion/completions
codex-metrics completion bash > ~/.local/share/bash-completion/completions/codex-metrics
exec $SHELL -l
```

If you are using a standalone binary by path, either invoke it by path when generating the completion script:

```bash
/path/to/codex-metrics completion zsh > ~/.zfunc/_codex-metrics
```

or move/symlink it into a directory on `PATH` before enabling shell completion.

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

Rebuild all local package artifacts and refresh the global self-host install:

```bash
make package-refresh-global
```

Refresh the local `.venv` install so `./.venv/bin/codex-metrics` matches the current built wheel:

```bash
make package-refresh-local
```

For a non-default install target:

```bash
make package-refresh-global INSTALL_SELF_ARGS="--target-dir /tmp/codex-metrics-bin"
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
