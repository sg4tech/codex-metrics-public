# ARCH-010: Integrate bandit security scanner into verify

## Problem

Security scanning is not enforced in CI/CD. Bandit (Python security linter) has been added as a dev dependency but is not yet integrated into `make verify` because there are 13 outstanding security issues to fix:

- **B110**: 2 instances of `try-except-pass` (silent exception suppression)
  - `src/ai_agents_metrics/commands.py:1014` — pricing loader
  - `src/ai_agents_metrics/observability.py:267` — debug log fallback
  - **Fix**: Replace `pass` with explicit `= None` or add proper logging

- **B608**: 11 instances of f-strings in SQL (SQL injection false positives)
  - `src/ai_agents_metrics/history_compare_store.py` (multiple lines)
  - `src/ai_agents_metrics/usage_backends.py:156`
  - **Context**: All use parameterized queries (`?` placeholders) + separate `params` list — safe from SQL injection
  - **Fix**: Add `# nosec B608` inline comments or rewrite without f-strings for clarity

Current state: `make bandit` runs separately but is excluded from `make verify`.

## Solution

1. Fix all B110 issues (explicit exception handling)
2. Suppress B608 issues with `# nosec B608` comments (safe patterns already in use)
3. Add `bandit` target to `make verify`
4. Verify in CI/CD that `make verify` passes

## Global skips rationale

`make bandit` runs with `--skip B404,B603,B607`. These are permanently skipped globally:

- **B404** (`import subprocess`) — the import itself is not a vulnerability; bandit treats it as an informational warning. Adding `# nosec` to every import line would be pure noise.
- **B603** (`subprocess_without_shell_equals_true`) — this rule fires when `shell=False` (the default and safer mode). It is the opposite of a real risk. No `shell=True` is used anywhere in this codebase.
- **B607** (`start_process_with_partial_path`) — all subprocess calls use standard system commands (`git`, `python`). Hardcoding full paths like `/usr/bin/git` would break portability without adding security in a developer tool context.

**B105** (`hardcoded_password_string`) is **not** globally skipped — it must be suppressed inline with `# nosec B105` where it fires. This keeps the rule active for real cases (e.g. an actual password literal added in future) while documenting each suppression explicitly.

## Acceptance Criteria

- [x] All B110 warnings fixed
- [x] All B608 warnings suppressed or fixed
- [x] `make bandit` passes cleanly (exit 0)
- [x] `bandit` is added to `verify` target in Makefile
- [x] `make verify` passes end-to-end

## Status

done

## Dependencies

None — can be picked up independently.
