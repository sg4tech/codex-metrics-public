# Pre-Push Security Scan in Wrong Repo Retro

## Situation

The `pre-push` security scan (check for forbidden internal markers before push) was wired
into the **private** repo instead of the **public** one. The public repo had `git_hooks.py`
with the correct `decide_verify_for_paths` + `run_verify` logic already in place, but no
`.githooks/pre-push` shell hook to invoke it.

Discovered during a hook audit. Fixed by removing `.githooks/pre-push` from the private repo
and adding it to the public repo.

## Timeline

| Commit | What happened |
|---|---|
| `885b9f7` | CODEX-32: first hook in private repo (`commit-msg`) |
| `a3926a2` | Added `pre-push` to **private** repo invoking `make verify` |
| `8fbf39a` | CODEX-42: added `pre-commit` to **public** repo — `pre-push` skipped |
| `77624ff` | Replaced private `pre-push` `make verify` with inline fast security scan |
| today | Removed private `pre-push`, added public `pre-push` |

## 5 Whys

**Why** was the security scan in the private repo?
→ `pre-push` was first created in the private repo (before the public repo existed) and was
never migrated.

**Why** wasn't it migrated when CODEX-42 wired up the public repo's hooks?
→ CODEX-42 added only `pre-commit` to the public repo. `pre-push` was out of scope for that
task — the focus was on the boundary verifier, not push-time verification.

**Why** wasn't the missing `pre-push` caught when `77624ff` refactored it?
→ `77624ff` worked on the existing private hook in isolation. The question "does this belong
here at all?" was never asked — refactoring an existing file implies it's in the right place.

**Why** wasn't the mismatch visible from the code?
→ The public `git_hooks.py` had the correct implementation (`decide_verify_for_paths` +
`run_verify`) but no shell hook to invoke it. The Python was ready; the wiring was missing.
Both repos had *something*, so neither looked obviously broken.

**Why** did the wiring get missed?
→ Hook setup was split across two tasks in two repos: Python logic landed in one pass,
the shell hook file was supposed to follow, and never did. There's no mechanism that enforces
"if `git_hooks.py` exports `pre-push` logic, a `.githooks/pre-push` must exist."

## Root Cause

Incomplete two-step migration: the Python side of the public pre-push hook was implemented
(in `git_hooks.py`) but the shell side (`.githooks/pre-push`) was never created. The gap
was invisible because the private repo still had a *working* hook — just in the wrong place.

## What Changed

- Removed `.githooks/pre-push` from the private repo (internal pushes don't need a boundary scan)
- Added `.githooks/pre-push` to the public repo (invokes `codex_metrics.git_hooks pre-push`)

## Why wasn't the question asked?

The commit `77624ff` was framed as an **optimisation**: "replace make verify with fast
security scan". When a task is framed as "make X faster", the agent inherits the existing
structure as correct and works within it — it doesn't ask "should X exist here at all?".

This is a structural property of how AI agents handle tasks: **the frame is inherited, not
verified.** Had the task been "make sure the security scan works correctly", the question
of which repo it belongs in would likely have surfaced. "Replace X with Y" — it doesn't.

## Prevention

**Robust (code-level):** add a test that enforces the structural invariant — if `git_hooks.py`
supports a hook, the corresponding `.githooks/<hook-name>` shell file must exist and be
executable. CI catches the gap automatically, independent of how a task is framed.

**Weaker (prompt-level):** when asking an agent to modify a hook, include "verify this
belongs in the right repo". Fragile because it requires the human to remember every time.

The general principle: **encode invariants in tests, not in task descriptions.**
