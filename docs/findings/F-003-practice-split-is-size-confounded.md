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

## Size-matched reanalysis (addendum, 2026-04-19)

After shipping the `derived_practice_events` table (Agent + Skill `tool_use` extractor), we re-ran the split on a larger warehouse — 160 threads instead of 88 — with size buckets by message count.

| Size bucket (messages) | n_with | n_without | median total tokens with | median total tokens without | ratio |
|---|---:|---:|---:|---:|---:|
| XS (≤20) | 9 | 35 | 1.1M | 0.4M | **2.9×** |
| S (21–50) | 10 | 31 | 6.6M | 2.6M | **2.5×** |
| M (51–100) | 7 | 17 | 20.0M | 7.9M | **2.5×** |
| L (101–200) | 10 | 21 | 43.3M | 18.8M | **2.3×** |
| XL (>200) | 10 | 10 | 115.3M | 102.2M | **1.1×** |

Two things happen when you size-match:

1. **The 20× gap collapses to ~2.5×** across XS–L buckets and to ~1.1× at XL — so most of the naive gap was task-size, as hypothesized.
2. **A ~2.5× gap persists after size-matching.** That is not zero. It decomposes into:
   - **Subagent-token share:** for practice-present threads, subagent sessions contribute a median 21.6% (mean 24.7%, max 83.6%) of total tokens. Subagent spawns are literally what `Agent` does, so this component is definitional, not an "inefficiency."
   - **Heavier main sessions:** main-session tokens/message is still ~1.37× higher for practice-present threads (M+L bucket, 177k vs 129k). Practice-using threads appear to carry more context per turn — review subagents feed back structured findings that the main session has to read.

So the honest statement is: **same-size threads that invoke practices spend ~2.5× more tokens, about half of which is the subagent overhead the practice itself creates, and about half is heavier main-session context-per-turn.** The XL bucket's 1.1× ratio hints that at large thread sizes this overhead saturates — but n=10/10 is too small to claim that.

**This still is not an effectiveness measurement.** We have controlled for thread size, not for task difficulty or outcome quality. "Did the practice produce a better result?" remains unanswered here; all we have shown is "size-matching does not explain the gap away."

## Related

- Practice distribution descriptive: [F-005](F-005-practice-distribution.md)
- Rework-based follow-up: [F-004](F-004-rework-signal-exists-but-n-too-small.md)
- Subagent-aliasing context: [F-001](F-001-claude-retries-are-subagents.md)
