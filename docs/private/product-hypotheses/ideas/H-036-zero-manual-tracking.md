---
id: H-036
title: Fully automatic session-based tracking may replace manual start/finish entirely
status: confirmed
created: 2026-04-11
confirmed: 2026-04-18
---

**2026-04-18 — Confirmed as product direction.** Founder's terminal decision: "я точно ничего руками ставить не буду" (will never hand-tag anything). Any user-visible metric must be derivable from history files alone. `events.ndjson` is retained as the tool's internal self-observation log (agent dogfood), but nothing user-facing reads from it. `start-task` / `finish-task` stay as agent-workflow gates inside this repo, not as product features. See `docs/private/product-strategy.md` amendment 2026-04-18 (final lock).

The hypothesis is confirmed as *direction*. Accuracy of LLM-based session clustering and goal-boundary detection is still open and is the next implementation question.

## Hypothesis

The current manual `start` / `finish` / `update` CLI workflow creates a permanent friction gap: attempt counts are never incremented, goal_type is often left as default, and notes/failure_reason fields are routinely skipped. As a result, the ledger is structurally correct but semantically shallow. Removing the manual layer and deriving all metrics from session history automatically may produce richer, more reliable signals at lower cost.

## Core idea

1. **Session as the atomic unit** — each conversation thread in the agent history is one implementation pass. Not a goal — a pass.
2. **Goal clustering, not session-as-goal** — a lightweight heuristic or LLM pass groups sessions into goals by comparing the first user message of each new session against known open goal descriptions. Sessions that continue the same intent become passes within one goal; sessions that shift intent open a new goal.
3. **Derived ledger** — `goal_id`, `title`, `pass_count`, `retry_count`, `status`, `cost_usd`, `tokens_*` are all computed from the warehouse pipeline, not entered manually.
4. **Retry pressure as COUNT GROUP BY goal_id** — trivially correct once clustering is accurate. No `--attempts` flag, no manual increment.

## Expected upside

- Retry pressure becomes accurate by construction, not by discipline.
- Eliminates the `start`/`finish` bookkeeping burden for the agent.
- Captures retries that currently go invisible (agent re-opens a new chat for the same task).
- Enables retrospective backfill: re-cluster historical sessions without re-running any work.
- Goal taxonomy (product / meta / retro) could be inferred from message content rather than passed as a flag.

## Main risks

| Risk | Notes |
|---|---|
| Clustering accuracy | LLM classifier may split one goal into two or merge two into one. Error rate needs empirical measurement. |
| Intent drift within session | One long session may contain multiple goal pivots; session-level granularity loses this. |
| Latency and cost of classification | Running an LLM on every new session adds latency and cost. Heuristic fallback (fuzzy title match) may be sufficient for 80% of cases. |
| Intentional multi-session goals | Some goals span many sessions by design (large tasks). High pass_count is not always retry pressure. Need a "planned multi-pass" marker. |
| Bootstrap and migration | Existing ledger goals need to be preserved or migrated; the new derived ledger must not break downstream CLI and report consumers. |

## Alternatives considered

- **Manual increment only**: require agent to always call `update --attempts N`. Rejected — proven unworkable in practice.
- **Warehouse-only aggregate signals**: expose `retry_rate` from `history_signals` without per-goal clustering. Simpler, already partially done (H-035, Chart 2 in render-html). Does not eliminate the manual ledger.
- **Hybrid**: keep manual ledger for goal_type and title, auto-derive pass_count and cost. Reduces friction without a full rewrite. Most practical near-term path.

## Open decisions

| # | Question |
|---|---|
| 1 | What is the minimum viable clustering heuristic that beats manual `attempts`? |
| 2 | Should the derived ledger replace `events.ndjson` or sit alongside it? |
| 3 | How do we handle intentional multi-session planning tasks vs retried implementation tasks? |
| 4 | What is the acceptable clustering error rate before the retry metric becomes misleading? |

## Confidence

Low — the direction is right, but accuracy of session clustering is unverified. Recommend a small spike: cluster the existing 87 warehouse threads for this project and manually validate groupings before committing to a full redesign.

## Relationship to other hypotheses

- Supersedes the manual-tracking concern in **H-002** (retry pressure as key metric) — same goal, different collection mechanism.
- Builds on **H-008** (historical conversation analysis as metrics input) — confirms the direction.
- Depends on **H-035** (history-derived retry pressure) as the near-term bridge while the full approach is validated.
