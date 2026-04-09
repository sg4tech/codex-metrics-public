# ARCH-009: Automate subprocess coverage without manual env toggle

**Priority:** low
**Complexity:** low
**Status:** open

## Problem

Coverage for subprocess-launched CLI invocations requires manually setting `CODEX_SUBPROCESS_COVERAGE=1`:

```bash
CODEX_SUBPROCESS_COVERAGE=1 make test
```

When this variable is set, `build_cmd` and `run_module_cmd` in `test_update_ai_agents_metrics.py` switch to `coverage run --parallel-mode`. Without it, subprocess calls produce no coverage data. This is a manual workaround, not a proper solution.

## Desired state

`coverage.py` supports automatic subprocess tracking via `COVERAGE_PROCESS_START` + a `.pth` file installed in `site-packages`. With this in place, all subprocess invocations are covered transparently — no env toggle, no test-code branching.

Steps:
1. Add `COVERAGE_PROCESS_START` to `pyproject.toml` coverage config (points to `pyproject.toml`)
2. Ensure the `.pth` file is installed in the venv (via `coverage` itself or `pytest-cov`)
3. Remove the `CODEX_SUBPROCESS_COVERAGE` branching from `build_cmd` and `run_module_cmd`
4. Verify subprocess coverage works with plain `make test`

## Acceptance criteria

- [ ] `make test` produces coverage data for subprocess-launched CLI calls without any extra env variable
- [ ] `CODEX_SUBPROCESS_COVERAGE` flag and related branching removed from test helpers
- [ ] `make verify` passes
