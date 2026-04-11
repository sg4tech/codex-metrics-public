# ARCH-011: Integrate radon for code complexity metrics

**Status:** open  
**Priority:** medium  
**Complexity:** low

## Rationale

Automated code quality metrics help identify overly complex functions and modules early. `radon` provides:
- **Cyclomatic complexity** — detects functions with too many decision paths (high complexity > 10 suggests SRP violation)
- **Maintainability Index** — aggregated score (0–100) combining LOC + complexity + Halstead metrics
- **Lines of Code (LOC)** — identifies modules that are too large and need decomposition

Current state: No automated complexity tooling beyond `pylint` and `mypy`.

## Implementation

1. Add `radon` to dev dependencies in `pyproject.toml`
2. Add `radon` check to `Makefile` (under a new `quality` target or extended `verify`)
3. Configure radon threshold in `pyproject.toml` or `.radon.ini`:
   - Cyclomatic complexity warning threshold: 10 (flag "complex" functions)
   - Maintainability Index warning: < 40 (flag hard-to-maintain modules)
4. Integrate into CI/CD: fail on complexity violations or add to pre-push hook
5. Document in `CLAUDE.md` how to run locally: `radon mi src/ -s`

## Acceptance Criteria

- [ ] `radon` is installed and runs without errors on `src/`
- [ ] Metrics for current codebase are baseline-documented (no failing violations yet)
- [ ] `make quality` (or `make verify`) runs radon checks
- [ ] Pre-push hook or CI warns on new violations
- [ ] Documentation added to project README or CLAUDE.md
