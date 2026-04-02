# File Immutability Bypass Retrospective

## Situation

We explored making `metrics/codex_metrics.json` effectively read-only at the operating-system level so the file would be harder to edit accidentally.

The implementation goal was valid, but the first pass introduced a test-oriented escape hatch that disabled the protection through a runtime environment variable.

## What Happened

- We added an OS-level immutability guard around metrics writes.
- We also added tests for the roundtrip path, the immutable guard contract, and the CLI workflow.
- To keep tests from leaving temporary files locked, a runtime bypass was introduced in production code.
- That bypass made the safety mechanism too easy to disable accidentally in a real run.
- The fix was to remove the runtime bypass, keep the real OS-level behavior, and make the tests use monkeypatching and fixtures instead.

## Root Cause

The root cause was scope leakage from testing into runtime behavior.

The temporary test convenience was allowed to become a production control path.
That weakened the very protection the change was supposed to add.

## Retrospective

The main lesson is that safety mechanisms should not depend on runtime “off switches” unless those switches are themselves part of the intended product contract.

For this repository, test bypasses belong in:

- dependency injection
- monkeypatched helpers
- test fixtures

They do not belong in the production code path as environment-based toggles unless we explicitly want an operator-facing feature.

The work also showed that coverage must include both the direct helper path and the subprocess-driven CLI path, otherwise tests can look green while hiding version or launcher assumptions.

## Conclusions

- The OS-level immutability idea is still viable as a hypothesis.
- The production implementation should not contain a hidden test bypass.
- Tests should validate the real behavior while using test-only control points to keep the environment clean.
- The CLI smoke coverage was useful because it exposed a mismatch between local assumptions and subprocess execution.

## Permanent Changes

- Classification:
  - tests or code guardrails
  - local policy clarification
  - retrospective only
- Added a local rule in `AGENTS.md` that test-only escape hatches should stay out of production code paths.
- Added tests for the immutability helper and the CLI workflow.
- Removed the runtime environment toggle from the production storage path.
- Kept the hypothesis open for real-world validation instead of declaring it done too early.
