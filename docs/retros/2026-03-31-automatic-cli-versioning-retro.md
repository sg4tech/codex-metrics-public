# Automatic CLI Versioning Retrospective

## Situation

We added explicit `--version` output for `codex-metrics`, but the first real usage immediately exposed a credibility problem:

- the command now showed a version
- but the version number still looked stale relative to the actual project history
- and different local execution surfaces could disagree about which code was running

This made the new version surface partially truthful but not yet trustworthy.

## What Happened

The first step added a standard top-level `--version` flag to the CLI and covered it with tests.

That improved visibility, but did not solve version discipline:

- `__version__` remained a manually edited constant
- README examples still hardcoded an old wheel filename version
- `.venv/bin/codex-metrics` could lag behind the source tree because the active local install was a normal installed copy in `site-packages`

We then:

1. moved the local development refresh path toward editable install via `make dev-refresh-local`
2. bumped the base package version from `0.1.0` to `0.2.0`
3. removed stale hardcoded version examples from README
4. replaced hardcoded version assertions in tests with package-driven assertions
5. finally changed version resolution so working repositories derive version strings from git state automatically

The resulting behavior is now:

- working repo: git-derived version
- source snapshot without `.git`: base version
- installed surface without source tree: installed package metadata

## Root Cause

The real problem was not "missing version output".

The real problem was that version identity was treated as static metadata while the tool had multiple runnable surfaces:

- source-tree execution
- editable local install
- installed wheel copy
- future standalone/global installs

That made a manually curated version string too weak to represent the actual command surface the user was invoking.

## 5 Whys

1. Why did `codex-metrics --version` feel wrong?
   Because it showed `0.1.0` even after substantial project evolution.

2. Why did it still show `0.1.0`?
   Because the package version was a manually maintained constant and had not been bumped often enough.

3. Why was manual bumping insufficient?
   Because the project had several runnable surfaces, and version discipline depended on people remembering both metadata updates and install refreshes.

4. Why did surface drift matter so much?
   Because the newly added `--version` flag turned hidden drift into visible inconsistency.

5. Why did the inconsistency persist after adding version output?
   Because the system answered "what version string is stored?" rather than "what code surface is actually running right now?"

## Theory of Constraints

The initial assumed constraint was missing CLI affordance: "users cannot see the version".

After that was fixed, the bottleneck moved one layer deeper:

- not observability of version
- but fidelity of version identity across runnable surfaces

The effective constraint was surface synchronization and version derivation strategy, not CLI formatting.

## Retrospective

The strongest move was not another manual bump process.

The strongest move was to make versioning more automatic and surface-aware:

- editable local refresh for day-to-day development
- git-derived version strings in working repositories
- metadata fallback for installed artifacts
- tests that reflect the actual surface under test instead of one universal hardcoded string

This followed the repository's strongest recurring pattern:

`diagnosis -> guardrail -> verification`

## Conclusions

- Explicit version output is necessary but not sufficient.
- A visible version surface makes stale-install drift immediately obvious.
- Manual version constants are too weak for multi-surface local tooling.
- Development and release surfaces must be treated separately.
- Version tests should validate the intended surface semantics, not force one identical string in every context.

## Permanent Changes

- `codex_metrics.__version__` now resolves from git metadata when a repository is present.
- Source snapshots without `.git` fall back to a stable base version.
- Installed surfaces fall back to installed package metadata.
- `make dev-refresh-local` is the canonical development refresh path for keeping `.venv` and source-tree execution aligned.
- Version tests now cover git-first and fallback resolution paths.
