# Retro: Personal email leaked into public sync branch via git subtree push

- Date: 2026-04-10
- Goal: 2026-04-10-002 (fail)
- Related: CODEX-59, PR #23 on sg4tech/ai-agents-metrics

## Situation

After completing CODEX-59 and running `make public-overlay-push`, PR #23 was opened on the public repo. It showed **357 commits** instead of the expected small diff, and **`glendemon@gmail.com`** appeared as the author email on a subset of those commits — a personal email that must not be exposed on the public repo.

## What Happened

1. `make public-overlay-push` runs `git subtree push --prefix=oss public sync`
2. `git subtree push` traverses the entire private repo history, extracts every commit that touched `oss/`, rewrites paths, and replays them individually onto the `sync` branch on the public remote
3. Among those historical commits are the "Merge pull request #N from sg4tech/sync" merge commits that GitHub created when previous PRs were merged on the public repo — those commits carry the user's personal GitHub email
4. These merge commits were imported into the private repo via `make public-overlay-pull` (which does `git subtree pull --squash`), but `--squash` only squashes them into a single commit in the *private* repo's `oss/` subtree history; the original commits and their authorship are still reachable via the git subtree split algorithm
5. The result: personal email reappears on the public sync branch with every new `make public-overlay-push`

## Root Cause — 5 Whys

**Why did personal email appear on the public sync branch?**
→ git subtree push replayed historical PR-merge commits that carried the personal email.

**Why were those commits in the subtree history?**
→ `public-overlay-pull` uses `git subtree pull`, which imports public history into the private repo's subtree tracking, including the original GitHub-authored merge commits.

**Why wasn't this caught before the push?**
→ The `make public-overlay-push` boundary check (`public-boundary-rules.toml`) only scans file *content* for forbidden strings; it does not inspect commit author metadata.

**Why wasn't the squash approach used from the start?**
→ The public overlay sync runbook did not specify that the sync branch must always be a single squashed commit. The assumption was that `git subtree push` would produce a clean, incremental diff — but it produces a full replay of the subtree history.

**Why was this not caught in the previous 22 PRs?**
→ It was — the user had given a previous instruction to clean the commit history before public pushes, which was not implemented as a permanent process step. The knowledge lived only in chat history, not in the runbook or automation.

## Theory of Constraints

The bottleneck is not awareness of the issue — it was known. The bottleneck is that **the correct push procedure (squash to 1 commit) was never encoded as the default execution path**. The runbook says "push, open PR, merge" without specifying the squash requirement. Without a codified constraint, the broken path remains the default.

## Conclusions

1. The `make public-overlay-push` flow must always produce a single squashed commit on `sync`, not a replay of subtree history.
2. The boundary check cannot catch metadata leaks (author email); this requires a separate git log scan.
3. A runbook instruction that is not enforced by automation or a test will be missed under time pressure.

## Permanent Changes

| Change | Scope | Status |
|--------|-------|--------|
| Rewrite `public-overlay-push` to always force-push a single squashed commit | `scripts/public_overlay.py` or `Makefile` | Pending |
| Add author-email check to boundary verification | `scripts/public_overlay.py` | Pending |
| Update `docs/private/public-overlay-sync.md` to document the squash requirement explicitly | Runbook | Pending |
| Check private repo for personal email and rewrite if needed | Private repo history | Deferred (user review) |

## What to Do Next

Before the next public push, the squash-to-one-commit behavior must be the default in `make public-overlay-push`, not a manual workaround applied after the fact. Until the script is fixed, the manual workaround is:

```bash
OSS_TREE=$(git rev-parse HEAD:oss)
PUBLIC_MAIN=$(git rev-parse public/main)
NEW_COMMIT=$(GIT_AUTHOR_NAME="Codex" GIT_AUTHOR_EMAIL="codex@example.com" \
  GIT_COMMITTER_NAME="Codex" GIT_COMMITTER_EMAIL="codex@example.com" \
  git commit-tree $OSS_TREE -p $PUBLIC_MAIN -m "Squashed oss/ changes through <tag>")
git push public "${NEW_COMMIT}:refs/heads/sync" --force
```
