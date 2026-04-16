# ARCH-014: Extract usage resolution functions out of cli.py

**Status:** done  
**Priority:** medium  
**Complexity:** medium

## Rationale

`usage_backends.py` and `commands.py` import from `cli.py` via lazy imports to work around a circular dependency:

```python
# usage_backends.py:187, 221
from ai_agents_metrics import cli as cli_module
cli_module.resolve_claude_usage_window(...)
cli_module.resolve_codex_usage_window(...)

# commands.py:1012
from ai_agents_metrics.cli import PRICING_JSON_PATH, load_pricing
```

These symbols (`resolve_claude_usage_window`, `resolve_codex_usage_window`, `PRICING_JSON_PATH`, `load_pricing`) live in `cli.py` but semantically belong in `usage_backends.py` or a dedicated `usage_resolution.py` module. The lazy import is a workaround, not a design.

The circular dependency also prevents adding an import-linter contract that enforces `usage_backends` as a lower layer than `cli`.

## Goals

- Move usage resolution logic out of `cli.py` into `usage_backends.py` or a new `usage_resolution.py` module
- Eliminate the lazy `cli` imports in `usage_backends.py` and `commands.py`
- After the move, add an import-linter contract: `usage_backends` must not import from `cli`

## Approach

1. Identify all symbols in `cli.py` that `usage_backends.py` and `commands.py` call
2. Move them to `usage_backends.py` (preferred, since they are backend-specific) or a new `usage_resolution.py`
3. Update `cli.py` to call the moved functions instead
4. Replace lazy imports in `usage_backends.py` and `commands.py` with normal top-level imports
5. Add import-linter contract: `ai_agents_metrics.usage_backends` must not import `ai_agents_metrics.cli`

## Acceptance Criteria

- [x] No lazy `cli` imports remain in `usage_backends.py` or `commands.py`
- [x] `make verify` passes without regressions
- [x] New import-linter contract added and passing: `usage_backends` must not import `cli`
- [x] `PRICING_JSON_PATH` and `load_pricing` live outside `cli.py` (in `usage_resolution.py`)
