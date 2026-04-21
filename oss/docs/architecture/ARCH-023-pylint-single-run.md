# ARCH-023: Collapse Tier 1/2/3 into a single default pylint run

**Status:** done
**Priority:** low
**Complexity:** low

## Rationale

ARCH-019 → ARCH-022 curated the pylint rule set by whitelisting ~28 codes
across three tiers. The Makefile ran pylint three separate times with
`--disable=all --enable=<tier>` flag combinations; pyproject expressed the
same whitelist via `disable = "all"` + `enable = [...]`. The tiered framing
was a staged rollout device — now that all three tiers hard-fail, the tiers
are a cost, not a feature:

- Three pylint invocations per `make verify` (~3× startup overhead).
- The rule list lives in two places (Makefile `--enable` flags AND
  `[tool.pylint."messages control"] enable`).
- Adding or removing a rule requires editing both Makefile and pyproject.
- The tier framing in output log lines is meaningless — every rule is
  build-blocking now.

## Implementation

### pyproject.toml

Flip from whitelist to blacklist mode:

```toml
[tool.pylint."messages control"]
# disable = "all" / enable = [ 28 codes ]   # removed
disable = [
    # Docstring-per-private-helper busywork.
    "missing-module-docstring",     # C0114
    "missing-class-docstring",      # C0115
    "missing-function-docstring",   # C0116
    # Fires on every @dataclass and Protocol — wrong signal for this codebase.
    "too-few-public-methods",       # R0903
    # Fires on the intentional cli.main dispatch chain enforced by
    # test_main_passes_runtime_facade_to_every_command_handler.
    "too-many-return-statements",   # R0911
    # Inline-disable meta-warnings — we deliberately use `# pylint: disable=`
    # throughout the codebase and don't want the meta noise.
    "locally-disabled",             # I0011
    "suppressed-message",           # I0020
    "use-symbolic-message-instead", # I0023
    # Naming is enforced by ruff; pylint's default conventions collide
    # with our _private_helper naming.
    "invalid-name",                 # C0103
    # Import-order signal is duplicated by import-linter contracts.
    "ungrouped-imports",            # C0412
    # Lambda assignment is legitimate in our adapter layers.
    "unnecessary-lambda-assignment", # C3001
    # Python 3 default — no need to flag `class Foo:` as implicit object.
    "useless-object-inheritance",   # R0205
    # W0718 broad-exception-caught covers bare `except:` usefully; W0702
    # is duplicated by ruff E722 with better messages.
    "bare-except",                  # W0702
    # FIXME markers are intentional debt pointers tracked in
    # docs/architecture/*.md follow-up sections.
    "fixme",                        # W0511
]
```

`[tool.pylint.design]`, `[tool.pylint.format]` (`max-line-length=250`), and
`[tool.pylint.similarities]` (`min-similarity-lines=40`) are unchanged and
now feed directly into the default run.

### Makefile

```makefile
pylint-check: check-init
	./.venv/bin/pylint src/
```

One invocation, no flag gymnastics. All rules come from pyproject.

### What this gains

- **Single source of truth.** Adding or removing a rule is a one-line
  pyproject edit.
- **Faster CI.** `make verify` pylint stage runs once (~10–15 seconds)
  instead of three times.
- **Honest framing.** Output shows a single `10.00/10` rating, matching the
  reality that every rule is blocking.
- **Easier onboarding.** A new contributor running `pylint src/` locally
  gets the same answer CI does, with no need to know about tiers.

### What this does NOT change

- The per-file `# pylint: disable=...` annotations added across ARCH-019
  through ARCH-022 stay in place with their documented rationale.
- The thresholds (max-args=8, max-locals=20, max-line-length=250, etc.)
  stay in `[tool.pylint.design]` / `[tool.pylint.format]` /
  `[tool.pylint.similarities]`.
- The excluded rules (C0114/C0115/C0116/R0903/R0911 and a handful of
  category-level noise rules) stay excluded — just now via an explicit
  `disable` list instead of via the inverse `enable` whitelist.

## Acceptance Criteria

- [x] `make pylint-check` is a single `pylint src/` invocation.
- [x] `pyproject.toml` has a `disable = [...]` list with one reason per
      entry, no `disable = "all"` / `enable = [...]` whitelist.
- [x] `make verify` clean: pylint 10.00/10 (single rating line), 480 tests
      pass, import-linter 6 kept / 0 broken.
- [x] No rule-code duplication between Makefile and pyproject.
