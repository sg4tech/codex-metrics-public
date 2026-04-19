# Findings

Measurements from running `ai-agents-metrics` against a single developer's 6-month Claude Code + Codex history (3.85B tokens, 160 threads, 334 sessions). Each finding is surprising or non-obvious enough that future analyses of AI-agent history should know about it.

All numbers are verifiable: the pipeline is deterministic and the warehouse schema is documented in [warehouse-layering.md](../warehouse-layering.md) and [data-schema.md](../data-schema.md).

## Index

| # | Finding | Headline number |
|---|---------|-----------------|
| [F-001](F-001-claude-retries-are-subagents.md) | 100% of Claude "retries" are subagent spawns, not user retries | 160 / 160 threads have `main_attempt_count = 1` |
| [F-002](F-002-claude-user-role-is-not-human.md) | Claude's `role='user'` is mostly not human-typed | 86.7% of `role='user'` events are `tool_result` or template |
| [F-003](F-003-practice-split-is-size-confounded.md) | Naive practice-effectiveness split is size-confounded | 20× token gap, 22× duration gap between "with code-review" and "without" |
| [F-004](F-004-rework-signal-exists-but-n-too-small.md) | Cross-thread file-rework signal is detectable but N=66 too small for claims | 61% of implementation threads have a rework follow-up; practice effect is within noise |

## Status

These are **N=1 findings**. They describe what we measured on one developer's history, not what is universally true across all AI-agent users. They are published because the *mechanisms* (subagent-aliased retry counts, `role='user'` pollution, size-confounded splits) are properties of the underlying tools (Claude Code, Codex) and will affect anyone running similar analyses — not just this dataset.

For discussion or replication on your own history: see [history-pipeline.md](../history-pipeline.md) for how to build the warehouse, [warehouse-layering.md](../warehouse-layering.md) for the data model.
