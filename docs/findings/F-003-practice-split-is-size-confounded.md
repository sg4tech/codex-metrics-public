# F-003 — Naive practice-effectiveness split is size-confounded

**Dataset:** 88 Claude Code threads, 3.85B tokens, 2026-04-19 measurement on `warehouse-full.sqlite`.

## TL;DR

The obvious way to measure "does practice X help?" is to split threads into those that used X and those that didn't, then compare outcomes. On this dataset, this split shows a **20× token gap** and **22× duration gap** between the two groups — but it is almost entirely a task-size confound. The practice fires on threads big enough to need it, not on threads where it would help.

## The setup

We wanted to test H-015: do AI-collaboration practices (code review, discovery/Explore, QA-pass) correlate with better outcomes (less tokens, shorter duration, fewer retries)?

Method: split 88 Claude threads by whether they had ≥1 `Skill:code-review` or `Agent:pr-review-toolkit:code-reviewer` event, compare outcome distributions.

## Result

| Split | With practice (n) | Without practice (n) | Median ratio (with / without) |
|---|---|---|---|
| code_review × total_tokens | 50M (18) | 2.5M (70) | **20×** |
| code_review × output_tokens | 164k (18) | 10k (70) | **17×** |
| code_review × duration | 27,500 s (18) | 1,300 s (70) | **22×** |
| code_review × main_sessions | 1 (18) | 1 (70) | 1× |
| code_review × subagent_sessions | 5 (18) | 0 (70) | n/a (both in single digits) |
| discovery (`Explore`) × total_tokens | 13M (15) | 2.5M (73) | **5×** |
| discovery × duration | 23,400 s (15) | 1,300 s (73) | **17×** |

## Why this is not effectiveness

Reading this table as "code-review reduces rework!" would be wrong. Reading it as "code-review causes 20× more tokens!" would be equally wrong. The right reading is:

**Practice-presence and task size are correlated because the practice is invoked when it's worth invoking.** Code-review fires on threads that produced code substantial enough to warrant review. Explore fires on tasks complex enough that the agent decides it needs to look around first. Trivial threads — "what does this error mean?", "format this date" — never trigger either practice, because there's nothing to review or explore.

So the 20× gap is measuring task complexity stratification, not practice outcome.

## The confound is multi-directional

- **"With-practice" threads are bigger.** More tokens, longer duration, more subagents.
- **"Without-practice" threads include a lot of trivial work.** The median thread without practices is 2.5M tokens / 22 min — probably a short question or small fix.
- **Some "without-practice" threads are research or discussion** — no code was produced, so no code-review was ever appropriate. These don't belong in an effectiveness comparison at all.

The split is not comparing "users who did X" vs "users who didn't" — it's comparing "tasks that needed X" vs "tasks that didn't".

## What would actually test practice-effectiveness

None of these are free; they are listed in order of "cheapest that might work":

1. **Within-thread segmentation.** When `Explore` fires in the first 20% of a thread, is the remaining 80% more efficient (lower tokens-per-Edit, shorter time-to-commit) than threads where `Explore` never fired early? Task size is held constant per thread.
2. **Matched-pair comparison.** For each practice-present thread, find 1–3 same-size practice-absent threads and compare normalized outcomes. Requires a size-matching function that isn't itself confounded.
3. **Project-level time-trend.** Did tokens-per-edit drop after the user started using skill X in project Y? Within-project, the task mix is more stable.
4. **Cross-thread rework rate.** Did threads that used a practice produce less file-rework in subsequent threads? See [F-004](F-004-rework-signal-exists-but-n-too-small.md).

All four need more methodology than a split comparison. All four still need enough practice-present N to get confidence intervals — on this dataset, with 18 code-review threads and 15 discovery threads, effect-size confidence bounds are wide enough that only large effects would be detectable.

## Implications

- **Do not read practice-split bar charts as effectiveness signals.** If someone publishes "teams that use code-review have X% better outcomes", ask whether the split is size-matched.
- **The naive split is still useful descriptively** — "18 of 88 threads used code-review, here's what those threads look like" is honest. It is not "code-review causes this."
- **N=1-developer data is structurally unable to support effectiveness claims at the thread level** without matched-pair or within-thread methodology. We had hoped to avoid that; we can't.

## Related

- Rework-based follow-up: [F-004](F-004-rework-signal-exists-but-n-too-small.md)
- Subagent-aliasing context: [F-001](F-001-claude-retries-are-subagents.md)
