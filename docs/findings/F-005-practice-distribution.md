# F-005 — What AI-coding practices actually fire in a real agent history

**Dataset:** 160 Claude Code threads / 334 sessions / 243 practice events, 2026-04-19 measurement on `warehouse-full.sqlite`. Data spans 2026-03-26 → 2026-04-17 (~3 weeks, single developer).

## TL;DR

Claude Code's `Agent` and `Skill` tool uses — the two structural signals for "the user or agent is invoking a named practice" — fire on **46 of 160 threads (29%)**. When they do fire, the distribution is heavy-tailed and skews toward **discovery and commit automation**, not toward code review. 20 distinct practice names cover all 243 events; the top 4 cover 55%.

## Why measure this at all

Before reasoning about whether a practice helps, you need to know whether anyone uses it. The `ai-agents-metrics` pipeline now ships `derived_practice_events` — a deterministic classifier over the `tool_use` blocks inside `raw_session_events` — specifically so this question has a reproducible answer rather than a vibes-based one.

This finding is purely descriptive: "here is what is being invoked." No effectiveness claim.

## Method

From each `raw_session_events` row whose payload contains `"type":"tool_use"`, we extract blocks whose `name ∈ {Agent, Skill}`. Each block is classified by a catalog:

- `Agent` blocks are keyed by `input.subagent_type` (e.g. `Explore`, `pr-review-toolkit:code-reviewer`).
- `Skill` blocks are keyed by `input.skill` (e.g. `commit-commands:commit`, `code-review:code-review`).
- Unknown names fall through to the `other` family so adding a new skill is additive, not lossy.

The classifier is versioned (`PRACTICE_EVENT_CLASSIFIER_VERSION`) so reclassification is idempotent unless the catalog changes. Source: [`oss/src/ai_agents_metrics/history/classify.py`](../../src/ai_agents_metrics/history/classify.py).

## Results — by practice family

| Family | Events | Distinct threads | Share of total |
|---|---:|---:|---:|
| discovery | 94 | 24 | 38.7% |
| commit_workflow | 48 | 20 | 19.8% |
| other | 38 | 9 | 15.6% |
| code_review | 34 | 18 | 14.0% |
| review_analysis | 11 | 4 | 4.5% |
| pr_review | 8 | 6 | 3.3% |
| test_analysis | 7 | 4 | 2.9% |
| metrics_review | 2 | 1 | 0.8% |
| planning | 1 | 1 | 0.4% |

**Discovery dominates.** Three agents contribute: `general-purpose` (54), `Explore` (31), `claude-code-guide` (9). Combined, they are 39% of all practice events and hit 15% of threads. Whatever else AI agents do, they spend a lot of calls on "look around the codebase before touching anything."

**Commit automation is #2.** Three related skills — `commit-commands:commit`, `commit-commands:commit-push-pr`, plain `commit` — total 48 events across 20 threads (12.5% of threads). Commit-workflow skills fire more often than code-review skills.

**Code review is a mid-tier practice, not the dominant one.** 34 events across 18 threads — less than commit automation, less than discovery. This contradicts the common narrative that "review the code the agent writes" is the load-bearing workflow.

**Planning is rare.** A single `Plan` agent invocation in a single thread. Either planning happens as implicit prose (not as a named tool), or it just isn't happening.

## Results — top individual practices

| Rank | Source | Practice name | Events |
|---:|---|---|---:|
| 1 | agent | `general-purpose` | 54 |
| 2 | agent | `<missing>` | 35 |
| 3 | agent | `Explore` | 31 |
| 4 | agent | `pr-review-toolkit:code-reviewer` | 26 |
| 5 | skill | `commit-commands:commit` | 22 |
| 6 | skill | `commit-commands:commit-push-pr` | 20 |
| 7 | agent | `claude-code-guide` | 9 |
| 8 | skill | `code-review:code-review` | 8 |
| 9 | agent | `pr-review-toolkit:pr-test-analyzer` | 7 |
| 10 | skill | `commit` | 6 |

The `<missing>` row is real: 35 `Agent` invocations carried no `subagent_type` input. These are free-form agent calls that the user (or a higher-level workflow) issued without naming a specific persona. Any classification pipeline that keyed on `subagent_type` only would silently drop these.

## Results — Agent vs Skill split

- `Agent` tool_use: 174 events (71.6%)
- `Skill` tool_use: 69 events (28.4%)

Named sub-agents fire ~2.5× more often than named skills. The raw `tool_use` count of course understates total token cost — each `Agent` call spawns a full sub-session that runs its own inference loop.

## Implications

1. **Practice-adoption is concentrated.** 29% of threads use any practice at all; within that 29%, the distribution is top-heavy. Studies that bin users into "uses AI-coding practices" vs "does not" will group almost everyone on one side.
2. **"Discover then commit" is the dominant observable pattern.** Discovery + commit_workflow = 58% of events and overlap on ~15% of threads. This is what AI-agent usage on a single developer's work actually looks like at the tool-use layer, regardless of what the marketing says about review-driven workflows.
3. **Catalog-gap risk.** 35 `Agent` invocations have no `subagent_type` and 38 events land in `other`. Any downstream analysis that slices by family should publish the `other`-share alongside its headline number.
4. **Descriptive findings can ship fast.** This finding shipped the same day the `derived_practice_events` table landed, because the classifier is structural and deterministic — no labeled data, no LLM scoring, no hand-annotation. The cost of building this view was catalog curation, not measurement.

## Related

- Size-confound + size-matched reanalysis: [F-003](F-003-practice-split-is-size-confounded.md)
- Retry-count aliasing that this classifier also protects against: [F-001](F-001-claude-retries-are-subagents.md)
- `role='user'` pollution — a different lens on "what is the agent actually doing": [F-002](F-002-claude-user-role-is-not-human.md)
