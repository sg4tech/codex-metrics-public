# F-008 — Per-skill compression ranking: which practice events actually save tokens

**Dataset:** Same 160-thread / 334-session Claude Code + Codex history as F-001 through F-007. Per-skill analysis across the 6 `practice_name` values with ≥8 events in `derived_practice_events`. Analyzed 2026-04-20.

## TL;DR

F-007 showed that, aggregated across all practice events, messages within 5 positions after an event use half the tokens of messages far from any event (median 2.05×, within-thread). That aggregate hid a wide split between skills. Decomposing by `practice_name`:

| Skill | Type | Events | N threads | Median far/near | 95% CI | Sign test |
|---|---|---:|---:|---:|---|---:|
| `pr-review-toolkit:code-reviewer` | agent | 26 | 11 | **3.25×** | [1.45, 5.94] | 9/11 |
| `general-purpose` | agent | 54 | 5 | 3.01× | [0.69, 5.88] | 4/5 |
| `Explore` | agent | 31 | 13 | **2.63×** | [1.71, 3.51] | **13/13** |
| `code-review:code-review` | skill | 8 | 6 | **2.55×** | [1.59, 6.57] | **6/6** |
| `commit-commands:commit-push-pr` | skill | 20 | 9 | 0.76× | [0.58, 2.38] | 4/9 |
| `commit-commands:commit` | skill | 22 | 4 | 0.72× | [0.49, 1.78] | 1/4 |

Three groups emerge:

1. **Strong compressors** (CI entirely above 1.2×, sign test ≥9/N): `Explore`, `code-reviewer`, `code-review`. Within-thread ratio 2.5-3.25×.
2. **High point estimate but wide CI** (N threads too small to call): `general-purpose` at 3.01× but CI [0.69, 5.88].
3. **Non-compressors, point estimate reverses sign**: `commit` and `commit-push-pr`, both below 1.0×. Near-event messages are *more* expensive than far-event ones.

## Why this decomposition matters

F-007's headline aggregate (2.05×) smuggled `commit`-family events (ratio ~0.72-0.76×) in with `Explore`-family events (ratio 2.63×). The two populations pull in opposite directions. A user reading the F-007 headline and inferring "practice events save tokens, use more of them" would act on a summary that is false for commit-family skills on this dataset.

Per-skill decomposition reveals the actual behavior: **subagent-spawning practices compress, scripted-workflow skills do not.** This is consistent with the F-007 mechanism test (Agent 2.01× aggregated vs Skill 1.20× aggregated) but sharpens it: the Skill aggregate is itself bimodal — `code-review:code-review` behaves like an agent (2.55×), the two `commit-commands` skills behave anti-compressively (<1.0×).

## Method

Replicates F-007 exactly, run per `practice_name` instead of pooled:

1. `derived_message_facts` filtered to `role='assistant'` with non-null `total_tokens`, ordered by `message_timestamp` per thread.
2. `derived_practice_events` filtered to a single `practice_name` at a time. For each assistant message, compute `dist = count of assistant messages between (latest prev practice ts of this skill, this msg ts]`.
3. Bucket: `near` if `dist ≤ 5`, `far` if `dist > 20`. Skip messages with no prior practice event of this skill.
4. Per thread: compute `median(far) / median(near)` if both sides have ≥3 messages.
5. Bootstrap 95% CI on the per-thread ratios (10 000 resamples, seed=42).

Replication check: pooled any-practice analysis yields median 2.00× [1.54×, 2.86×] on N=29 threads, matching F-007's reported 2.05× [1.23×, 2.47×] on N=28 within bootstrap noise. The method is unchanged; the split is the only new thing.

## Results in detail

### Strong compressors

**`Explore`** — 13/13 threads show `ratio > 1.0`. Binomial p-value under null ratio=1 is p ≈ 0.00012. This is the cleanest single result in the dataset: every thread that used Explore showed main-session compression after the call.

**`pr-review-toolkit:code-reviewer`** — 9/11 above 1.0, median 3.25×. Highest point estimate among strong-CI skills. Matches the expected mechanism — code-reviewer agent reads files and returns a compact review, main session receives only the summary.

**`code-review:code-review`** (skill, not agent) — 6/6 above 1.0, median 2.55×. Anomaly: classified as `skill` in the warehouse but behaves like an agent. Most likely explanation is that the skill internally spawns a subagent (Task tool call) even though the event is recorded as skill-kind.

### Non-compressors

**`commit-commands:commit`** — 1/4 above 1.0, median 0.72×. Near-commit messages use ~1.4× more tokens than far-commit messages. Mechanism is the opposite of compression: commit skills run inline, read git diff, touch multiple files, and expand context rather than isolate it.

**`commit-commands:commit-push-pr`** — 4/9 above 1.0, median 0.76×. Same direction as `commit`.

Both commit skills have wide CIs that straddle 1.0× on the upper bound, so the "near-commit is more expensive" claim is weakly supported. The claim that can be made strongly: **these skills do not compress** — the point estimate is firmly below 1.0× on limited data, and they do not appear in the strong-compressor group.

### Indeterminate

**`general-purpose`** — 54 events across only 5 usable threads. Point estimate 3.01× is high but CI [0.69, 5.88] crosses 1.0×. Event-concentration (10+ events per thread) likely reflects a specific workflow pattern that is not representative of the rest of the dataset. Needs broader data to rank.

## Limitations

**1. Subagent-to-skill classification is imperfect.** `code-review:code-review` is labeled `skill` in the warehouse but behaves like a subagent (compression = 2.55×). The kind label is a syntactic property of the tool call, not a semantic property of the behavior. Treating `source_kind` as a proxy for "does this event offload context" is an approximation that fails for any skill that invokes the Task tool internally.

**2. Small N per skill.** Only `Explore` (13), `code-reviewer` (11), and `commit-push-pr` (9) clear 8 threads; the rest are on 4-6 threads. Directional claims (which skills compress and which don't) are robust to sample size; absolute magnitude estimates are not.

**3. Within-thread design still has the "skill invoked when conversation was about to simplify anyway" limitation from F-007.** The design rules out task-size, task-type, and developer-state confounds, but not behavioral confounds — users may call `Explore` at moments where main-thread expansion was about to slow regardless. Proving this requires randomized injection, which is not possible retrospectively. The relative ranking (Explore vs commit) is less affected by this than the absolute magnitude.

**4. Codex skills under-represented.** The warehouse has more Claude Code practice events than Codex ones (practice-event extraction covers Claude's Task tool and skill invocations better than Codex's AGENTS.md-driven behavior). Cross-provider skill coverage is not equal.

**5. N=1 developer.** This is the same developer's archive used for F-001 through F-007. Personal skill-use patterns may drive the ranking. Replication across developers is required to separate general skill behavior from personal use patterns.

## Implications

For skill-use decisions on this dataset:

- **Keep invoking `Explore`, `code-reviewer`, `code-review:code-review`** — these reliably compress main-session context 2.5-3.25× within the same thread. The 13/13 and 6/6 sign tests leave no room for "maybe it doesn't help here."
- **Don't use commit-family skills for cost optimization.** They have other uses (consistent workflow, commit-message quality, hook invocation) — this finding does not speak to those uses. But if the reason to invoke a skill is token economy, `commit` and `commit-push-pr` do not deliver it on this dataset.
- **`general-purpose` is a black box.** 3.01× median with CI [0.69, 5.88] means it *might* be the biggest compressor or might be net-neutral. Using it for cost reasons is a coin flip until broader data arrives.

For future practice-event analyses:

- Aggregate "practice effect" numbers are misleading when the underlying skill set is heterogeneous. Prefer per-skill decomposition from the start.
- The Agent/Skill `source_kind` split is a useful first cut but not a reliable predictor of compression behavior (see `code-review:code-review`). If the skill internally spawns a subagent, it compresses. The event label alone does not tell you.

## Reproduction

- Warehouse: `warehouse-full.sqlite` (see [history-pipeline.md](../history-pipeline.md))
- Tables: `derived_message_facts` (role='assistant', `total_tokens IS NOT NULL`), `derived_practice_events` filtered per `practice_name`
- Method: identical to F-007 per-thread analysis, run once per skill; bootstrap 10 000 resamples, seed=42
- Related findings: [F-005](F-005-practice-distribution.md) (which practices exist), [F-007](F-007-practice-within-thread-compression.md) (aggregated compression effect and mechanism test)
