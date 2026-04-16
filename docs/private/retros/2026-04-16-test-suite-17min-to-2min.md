# Retrospective: test suite 17 min -> 2.5 min

## Situation

`make verify` took ~17 minutes to complete. The test suite alone (423 tests) consumed ~15 minutes (908s). This made the development feedback loop painfully slow: every change required waiting 17 minutes for verification, or developers would skip verification and risk regressions.

## What happened

Investigation revealed that the test suite was dominated by subprocess overhead and redundant file I/O, not by test logic complexity. Every CLI test spawned a fresh Python interpreter via `subprocess.run()`, and every test fixture copied the entire `src/` tree into a temp directory.

Two changes were applied:

1. **pytest-xdist** (`-n auto`): parallelized test execution across CPU cores. Result: 908s -> 191s (4.7x).
2. **In-process CLI execution**: replaced `subprocess.run([sys.executable, script, *args])` with direct `main()` calls inside the test process, eliminating Python startup overhead. Simplified repo fixtures by removing `shutil.copytree(src/)`. Result: 191s -> 51s (3.7x on top of xdist).

Combined: 908s -> 51s for tests, ~17min -> ~2min 40s for full `make verify`.

A small number of tests (install-self, bootstrap wrapper, script shim version, parallel lock test) were kept on subprocess because they inherently test subprocess-specific behavior (launcher scripts, entrypoint resolution, process-level parallelism).

## Root cause: 5 Whys

**Why was `make verify` slow?**
Because pytest took 15 minutes for 423 tests.

**Why did pytest take 15 minutes?**
Because each test averaged ~2 seconds, despite being logically simple. The time was spent on subprocess startup and file copying, not on actual test logic.

**Why did every test use subprocess?**
Because the original test infrastructure was written as end-to-end integration tests: spawn a fresh Python process, pass CLI arguments, capture stdout/stderr. This was the simplest correct approach when the test suite was small and fast enough.

**Why wasn't this noticed earlier?**
Because the test count grew incrementally (from ~50 to 423) and each individual test was only ~2s slow. The total time degraded gradually. There was no performance budget or regression check on test suite duration.

**Why was there no performance guard?**
Because `make verify` was treated as a correctness gate, not a productivity tool. Its runtime was never measured or tracked as a metric. The friction accumulated silently until the pain became obvious.

## Conclusions

1. The root bottleneck was not test logic but test infrastructure: subprocess-per-invocation and copytree-per-fixture.
2. In-process CLI testing (calling `main()` directly with captured stdout/stderr and `os.chdir`) is safe when tests use isolated `tmp_path` directories and don't depend on subprocess-specific behavior.
3. pytest-xdist was the lowest-effort, highest-impact change (2 lines, 4.7x speedup).
4. A small set of tests genuinely need subprocess (testing launcher scripts, entrypoints, process-level locking) — these were kept as-is.

## Permanent changes

### Code changes
- Added `pytest-xdist` to dev dependencies, configured `addopts = "-n auto"` in `pyproject.toml`.
- Added `run_cli_inprocess()` helper in `conftest.py` that calls CLI `main()` in-process with cwd/stdout/stderr capture.
- Switched `run_cmd()` in `test_metrics_cli.py` and `test_history_ingest.py` (imported by normalize/derive) to use in-process execution by default, with subprocess fallback for coverage mode.
- Simplified repo fixtures: removed `shutil.copytree(ABS_SRC)` from the default path; kept script file copy for subprocess-dependent tests.

### Guardrails
- Added `pytest-timeout = 5` in `pyproject.toml` — any single test exceeding 5 seconds will hard-fail. This catches regression toward subprocess-heavy tests before they accumulate.

### Classification of changes
- pytest-xdist + in-process runner: **code guardrails** (applied)
- pytest-timeout 5s budget: **code guardrails** (applied)
- Fixture weight audit: **retrospective only** (awareness, not automation)
