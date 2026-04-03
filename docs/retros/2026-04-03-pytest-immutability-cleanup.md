# Retrospective: pytest `rm_rf` cleanup warnings from immutable temp files

## Situation

During local test runs, pytest emitted cleanup warnings like:

- `(rm_rf) error removing ... Directory not empty`
- `PermissionError: [Errno 1] Operation not permitted`

The warnings were noisy, non-deterministic across runs, and were coming from temporary pytest directories on macOS.

## What Happened

The warnings were traced to tests that exercised metrics-file immutability on Darwin via `chflags uchg`.

Some tests correctly unlocked the exact metrics file they touched, but other test paths created additional immutable files under `tmp_path` and did not remove the immutable flag before pytest teardown. When pytest later tried to clean those directories, removal failed, the directories were moved into `garbage-*`, and later runs kept retrying cleanup and re-printing warnings.

## Root Cause

The immediate cause was incomplete teardown coverage for OS-level immutable files created in tests.

The deeper cause was that our test suite allowed real filesystem immutability side effects while assuming per-test cleanup was narrow enough to unlock only one known path.

## 5 Whys

1. Why did pytest print `rm_rf` warnings?
Because it could not delete temporary directories during cleanup.

2. Why could it not delete those directories?
Because some files inside them still had the immutable flag set on macOS.

3. Why were immutable files left behind?
Because teardown only unlocked one expected metrics file, not every immutable file created by the test flow.

4. Why was teardown that narrow?
Because the tests were written around the happy-path artifact location rather than around the real cleanup contract of the whole temp tree.

5. Why did that assumption survive?
Because we did not have a guardrail that exercised pytest cleanup behavior under real Darwin immutability semantics.

## Theory Of Constraints

The bottleneck was not pytest itself and not temp directory handling in general. The constraint was uncontrolled real OS-level file immutability in tests. Once teardown reliably removed that state from the affected temp tree, the cleanup warnings stopped for fresh runs.

## Retrospective

The useful lesson here is that tests touching filesystem protection features need cleanup logic scoped to the full side-effect surface, not just the primary artifact under assertion.

The first attempted fix was too local and only covered one fixture path. The second attempted fix overreached by deleting the entire temp tree and interfered with pytest's `--basetemp` lifecycle. The final fix was the narrow correct one: keep pytest in charge of temp directories, but proactively remove immutable flags from files created inside `tmp_path`.

## Conclusions

- The warning source was our own test-side Darwin immutability behavior, not a generic pytest bug.
- Historical `garbage-*` folders can keep surfacing old warnings even after the underlying bug is fixed.
- The safest permanent fix is to clear immutable flags during test teardown without taking ownership of directory deletion from pytest.

## Permanent Changes

- Added a shared test teardown in `tests/conftest.py` that removes immutable flags from files under `tmp_path`.
- Expanded temp-repo fixture cleanup in `tests/test_update_codex_metrics.py` so it unlocks all created files, not just `metrics/codex_metrics.json`.
- Verified a fresh run with a clean `--basetemp` and `-W error::pytest.PytestWarning`.

## Classification Of Follow-up

- Tests or code guardrails: keep the new teardown coverage in test infrastructure.
- Retrospective only: document that historical `garbage-*` folders may need one-time cleanup after fixing test-side immutability leaks.
- No action: no production-code policy change is needed from this incident.
