# Retro: test hardcoded interpreter name in --version assertion

**Date:** 2026-04-12

## Situation

`test_module_entrypoint_exposes_cli_version` asserted that `--version` output starts with the literal string `"python -m ai_agents_metrics "`. The test passed on CI and in most local setups but started failing after upgrading to Python 3.14 installed via Homebrew.

## What happened

The test ran subprocess via `sys.executable` (line 94 in `run_module_cmd`), which resolves to the actual interpreter binary. Inside a venv the symlink is typically named `python`, so `%(prog)s` in argparse produced `python -m ai_agents_metrics`. But when pytest was invoked through the system interpreter (`python3.14`) or when the venv symlink retained the versioned name (`python3.14`), the output became `python3.14 -m ai_agents_metrics` — and the hardcoded `startswith("python -m")` check failed.

Failure message:
```
AssertionError: assert False
  where False = 'python3.14 -m ai_agents_metrics 0.0.0.dev573+...'.startswith('python -m ai_agents_metrics ')
```

## 5 Whys

1. **Why did the test fail?** — The output string started with `python3.14`, not `python`.
2. **Why was the output different?** — `%(prog)s` in argparse uses the basename of `sys.argv[0]`, which is the interpreter binary name.
3. **Why was the interpreter binary name different?** — Homebrew Python 3.14 installs as `python3.14`; venv symlink names vary.
4. **Why didn't the test account for this?** — The assertion was written as a literal string match, assuming the interpreter is always named `python`.
5. **Why wasn't this caught earlier?** — CI and previous local runs used a venv where the symlink happened to be named `python`. The assumption was never tested against a versioned interpreter name.

## Root cause

The test asserted an exact interpreter name (`python`) that is an environment-dependent artifact, not a behavioral invariant. The actual invariant is: the output matches `<interpreter> -m ai_agents_metrics <semver>`.

## Fix

Replaced the literal `startswith` + exact regex with a single flexible regex:

```python
# Before
assert output.startswith("python -m ai_agents_metrics ")
assert re.fullmatch(r"python -m ai_agents_metrics \d+\.\d+.*", output)

# After
assert re.fullmatch(r"python[\d.]* -m ai_agents_metrics \d+\.\d+.*", output)
```

## Conclusions

- Tests that assert on subprocess output involving interpreter names, paths, or platform-dependent strings are brittle. The assertion should match the **invariant** (module name + version format), not the **incidental** (exact binary name).
- This is the same class of problem as hardcoding `/usr/bin/python` in shebangs — the name `python` is not guaranteed anywhere.

## Permanent changes

- **Test fix:** regex now accepts `python`, `python3`, `python3.14`, etc. via `python[\d.]*`.
- **No AGENTS.md change needed** — this is a general testing hygiene issue (don't hardcode environment artifacts), not a project-specific rule.
