# Retro: test/impl gap in public boundary — render_public_boundary_report_json

**Date:** 2026-04-08

## Situation

CI on `sg4tech/codex-metrics-public` failed with an `ImportError` at test collection time:

```
ImportError: cannot import name 'render_public_boundary_report_json'
from 'codex_metrics.public_boundary'
```

The test `test_handle_verify_public_boundary_prints_json` existed in `oss/tests/test_public_boundary.py`
and imported `render_public_boundary_report_json`, but the function was never implemented in
`src/codex_metrics/public_boundary.py`.

## What happened

- A test was written (or kept) in `oss/tests/` that referenced a function not yet implemented.
- `make verify` in the private repo runs `tests/`, not `oss/tests/`. The private test suite has no
  equivalent test for the JSON render path, so the gap went undetected locally.
- The failure only surfaced in public CI after `make public-overlay-push` delivered the code.

## Root cause

`oss/tests/` is not executed as part of `make verify` in the private repo. The private repo treats
`oss/` as a subtree artifact — content is verified at boundary level (`make verify-public-boundary`)
but not functionally tested against the private Python environment.

This means a test can exist in `oss/tests/` that references a non-existent symbol and the private
validation layer will not catch it.

## 5 Whys

1. **Why did CI fail?** — `render_public_boundary_report_json` was imported but not defined.
2. **Why was it undefined?** — The function was referenced in a test but never implemented.
3. **Why was the missing implementation not caught locally?** — `make verify` runs `tests/`, not
   `oss/tests/`.
4. **Why does `make verify` not run `oss/tests/`?** — No explicit rule; the private test target
   was written before `oss/tests/` existed as a meaningful test suite.
5. **Why was the test not caught when it was written?** — The test was likely written ahead of the
   implementation and the implementation was forgotten, or it arrived via a subtree pull before the
   private implementation was added.

## Conclusions

The public test suite (`oss/tests/`) can silently diverge from the public source (`oss/src/`) if
private `make verify` does not also run it. The current setup catches boundary violations and file
layout issues, but not import-level correctness of the public code.

## Fix applied

- Implemented `render_public_boundary_report_json` in `public_boundary.py`.
- Wired `handle_verify_public_boundary` to use it when `args.json` is set.
- All 350 private tests pass; public CI unblocked.

## Permanent changes to consider

| Change | Scope | Decision |
|--------|-------|----------|
| Add `oss/tests/` run to private `make verify` (or a separate `make verify-oss` target) | `AGENTS.md` / Makefile | **deferred** — adds ~1s overhead, low frequency of oss/ test changes; revisit if this gap recurs |
| Require that any symbol imported in `oss/tests/` exists in `oss/src/` (enforced by public CI) | public CI is already the backstop | **already in place** — public CI catches it, just later than ideal |
| When adding a test that references a new function, implement the function in the same commit | working style | **note added to AGENTS.md** |
