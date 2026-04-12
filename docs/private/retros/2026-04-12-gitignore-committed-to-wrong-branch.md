# Retro: .gitignore fix committed to master instead of feature branch

**Date:** 2026-04-12
**Severity:** Minor (easily corrected, no data lost)

---

## Situation

During task CODEX-64 (warehouse-missing error UX fix), a `.gitignore` issue was identified: `.venv` symlinks were not ignored because the existing `.venv/` pattern only matches directories, not symlinks. The fix was a two-line addition.

## What happened

The agent committed and pushed the `.gitignore` fix directly to `master` instead of adding it to the active feature branch `claude/nifty-gauss`. When the user asked to push, the commit was already on `master` and had been pushed to `origin/master`.

## Root cause

The agent was operating in a worktree (`nifty-gauss`) but ran the `.gitignore` edit and commit from the main repo root (`/Users/viktor/PycharmProjects/codex-metrics`) where `master` is checked out. No check was done to confirm which branch the working directory corresponded to before committing.

## 5 Whys

1. **Why was `.gitignore` committed to master?** — The edit and commit were run from the main repo root, which is on `master`.
2. **Why was the main repo root used?** — The `git push` for the feature branch had failed from the worktree path; the agent switched to the main repo root to retry, and then continued working there without switching back.
3. **Why was there no branch check before committing?** — The agent didn't verify current branch before running `git add` + `git commit`.
4. **Why was the fix done outside the task scope at all?** — The `.gitignore` gap was discovered as a side effect of debugging the pre-commit hook failure, and the agent fixed it in place without pausing to confirm the right target branch.
5. **Why wasn't the user asked first?** — The agent treated it as a trivial NO-TASK config fix and assumed direct-to-master was acceptable, without confirming.

## Retrospective

The error was low-impact (the fix is correct, the branch got the same commit, and master now has the fix too), but the process was wrong:

- A worktree session should never produce commits on `master` as a side effect.
- Before any `git add` + `git commit`, the agent must confirm the current branch matches the intended target.
- Fixes discovered as side effects during a task should be staged on the task branch, not committed ad hoc to whatever branch happens to be checked out.

## Conclusions

1. Always run `git branch --show-current` before committing, especially after switching between repo roots and worktrees.
2. In a worktree session, all commits go to the worktree branch unless the user explicitly requests otherwise.
3. Side-effect fixes (like `.gitignore`) discovered during a task belong on the task branch, not master.

## Permanent changes

- **AGENTS.md:** Add rule — in worktree sessions, all commits go to the worktree branch. Verify current branch before committing.
- **Retrospective only:** The specific `.gitignore` / symlink detail does not need a wider policy entry.
