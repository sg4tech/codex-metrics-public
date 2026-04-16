# Retro: Make verify overuse during ARCH-014

**Date:** 2026-04-16  
**Task:** ARCH-014 — Extract usage resolution out of cli.py

## Situation

During ARCH-014 implementation, `make verify` / `make verify-fast` were run 3 times:
1. After initial implementation — to catch lint errors
2. After fixing lint errors — to re-check
3. Final run before committing

Runs 1 and 2 were unnecessary and expensive (~55s and ~1.5min each).

## What happened

After lint errors appeared, instead of running `ruff check <file>` to re-verify just the lint fix, the agent ran `make verify-fast` again. Then ran `make verify` and piped it through grep to extract the exit code — which could be done with `echo $?` or by inspecting the actual output.

## Root cause

No clear mental model of when to use heavy suite vs. targeted commands. Defaulted to the full suite at every checkpoint instead of reserving it for the final gate.

## Conclusions

**Rule: `make verify` / `make verify-fast` are final-gate commands only — run once before committing.**

For intermediate checks, use targeted commands:

| Need | Command |
|------|---------|
| Lint fix verification | `ruff check <file>` or `ruff check <file> --fix` |
| Import check | `python3 -c "import ai_agents_metrics.cli"` |
| Type check one file | `mypy src/ai_agents_metrics/<file>.py` |
| Import-linter contracts | `lint-imports` |
| One test module | `pytest tests/test_X.py -x -q` |
| Exit code check | `echo $?` after the command |

## Permanent changes

- None needed in code
- Rule captured in memory (see feedback_make_verify_usage.md)
