# Retro: PEP 639 License Classifier Conflict

**Date:** 2026-04-09  
**Severity:** Low (CI failure, 1-line fix, no data loss)  
**Time lost:** ~15 minutes

---

## Situation

Added `keywords` and `classifiers` to `pyproject.toml` to improve PyPI discoverability.
One of the classifiers was `License :: OSI Approved :: Apache Software License`.
The project already had `license = "Apache-2.0"` (PEP 639 SPDX expression).

CI failed on `make init` (`pip install -e .`) with:

```
setuptools.errors.InvalidConfigError: License classifiers have been superseded
by license expressions. Please remove: License :: OSI Approved :: Apache Software License
```

Local `make verify` passed cleanly. The error was invisible locally.

---

## What Happened

1. Wrote `classifiers` block in `pyproject.toml` without reading the PEP 639 spec
2. Ran `make verify` locally — passed (lint, typecheck, tests all green)
3. Pushed to public repo via `public-overlay-push`
4. CI failed during `make init` (`pip install -e .`)
5. Root cause identified: PEP 639 prohibits `License ::` classifier when `license =` SPDX expression is present
6. Fixed in one line, pushed fix

---

## 5 Whys

**Why did CI fail?**  
`License :: OSI Approved :: Apache Software License` classifier conflicts with `license = "Apache-2.0"` — setuptools ≥82.x enforces PEP 639 and rejects both simultaneously.

**Why was the conflicting classifier added?**  
Classifiers felt like "safe additive metadata." The existing rule "read official packaging docs before writing pyproject.toml fields" was not applied — the assumption was that classifiers are a list you freely extend, not a field with a cross-field constraint.

**Why wasn't PEP 639 checked?**  
The rule exists in memory and CLAUDE.md but applies to "new fields or formats." Classifiers felt like an extension of a known pattern, not a new format requiring a spec check. The constraint between `license =` and `License ::` classifiers was not in our mental model.

**Why didn't `make verify` catch this locally?**  
`make verify` = lint + security + typecheck + pytest. It does NOT run `pip install -e .`. The PEP 639 enforcement happens during the package install step. Local setuptools was older than CI's setuptools 82.x — the error was enforced only in CI.

**Why doesn't `make verify` include a package install check?**  
The package build was never in the local verification loop. The implicit assumption was: if tests pass, the package is valid. This is false — test suite passes ≠ package installable. No one ever added a packaging validation step to `verify`.

---

## Root Cause

`make verify` does not validate that `pip install -e .` succeeds. Local setuptools version diverges from CI's version silently. Any `pyproject.toml` change that is valid for old setuptools but invalid for new setuptools will pass `make verify` locally and fail in CI.

The missing knowledge (PEP 639 constraint) is a contributing factor, but it's the secondary cause. The primary cause is the gap in the verification loop.

---

## Theory of Constraints

The bottleneck is not missing rules — the rule "read packaging docs" exists. The bottleneck is missing enforcement: the local verification loop does not test the same thing as CI. Knowledge without enforcement is not a guardrail.

The constraint: any packaging metadata error is only caught when CI runs `make init`. This is a delayed feedback loop.

---

## Permanent Changes

### 1. Add `setuptools>=82` to dev deps (code guardrail)

Pin local setuptools to a version that enforces PEP 639. Local env now diverges less from CI.

### 2. Add `build-check` to `make verify` (code guardrail)

Add a target that runs `pip install --no-deps -e .` and include it in the `verify` chain.
This validates packaging metadata cheaply — no full wheel build, no test run, just metadata + install hooks.

### 3. Update AGENTS.md (local project rule)

After any `pyproject.toml` change: `make build-check` must pass before pushing.
This makes the new target discoverable and expected.

---

## Conclusions

- `make verify` passing is not sufficient proof that a `pyproject.toml` change is safe
- "Read packaging docs" is a necessary but not sufficient guardrail — enforcement via tooling is required
- Local setuptools version must be pinned to match CI's minimum version
- The fix is cheap; the detection delay is the real cost
