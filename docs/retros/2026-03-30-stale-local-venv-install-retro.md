# Stale Local Venv Install Retrospective

## Situation

We had already improved the standalone bootstrap and installer flow, and the current source tree correctly supported:

- `--command-path`
- repo-local `tools/codex-metrics`
- better bootstrap-generated agent instructions

But in local use the command still behaved like an older build.

That created a confusing mismatch:

- the current source was correct
- the standalone artifact was correct
- but the command actually running in the shell was still stale

## What Happened

The failing path was:

1. Build fresh standalone artifacts.
2. Reinstall the global self-host binary.
3. Run `codex-metrics ...` from an active virtualenv.
4. Observe old help output and old behavior.

The wrong mental model was that refreshing the global standalone install would also refresh the locally active command.

It did not.

`which codex-metrics` resolved to:

- `.venv/bin/codex-metrics`

And that entrypoint imported `codex_metrics` from:

- `.venv/lib/.../site-packages`

That package had not been refreshed, so the shell kept running the older installed wheel.

## Root Cause

The old make flow refreshed only part of the local delivery surface.

It updated:

- `dist/`
- the standalone self-host install

But it did not update:

- the installed package inside `.venv`

So there were effectively two local runnable surfaces:

1. standalone/global
2. venv-installed package

Only one of them was being refreshed.

## Retrospective

This was a real failed path in the local operator workflow.

The mistake was treating “local refresh” as if there were only one local executable surface.

In practice, for this repository there are at least two:

- `dist/standalone/codex-metrics`
- `.venv/bin/codex-metrics`

If only one is refreshed, then local testing and real usage can drift immediately.

That is especially easy to miss when an activated virtualenv silently shadows the global command.

## Conclusions

- Local refresh must include the active `.venv` install, not only standalone/global surfaces.
- When debugging CLI drift, `which codex-metrics` and the actual import location matter more than assumptions about the latest build.
- A working standalone artifact does not prove the current interactive shell is using that artifact.

## Permanent Changes

- Added `make package-refresh-local` to rebuild artifacts and force-reinstall the current wheel into `.venv`.
- Made `make package-refresh-global` depend on `package-refresh-local` before rebuilding and reinstalling the standalone binary.
- Added installer-side shadowing warnings so users are told when an active virtualenv is overriding the global install.
- Keep using `which codex-metrics` and import-path verification as a standard diagnostic step whenever local CLI behavior looks stale.
