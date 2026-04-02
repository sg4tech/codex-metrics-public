# Late Task Start Bookkeeping Retrospective

## Situation

During the current `codex-metrics` work on agent-agnostic and Claude-related support, meaningful engineering progress started before the task was opened in `codex-metrics`.

The user correctly called this out.

For this repository, metrics bookkeeping is not optional metadata. It is part of the operational workflow and part of the definition of done.

## What Happened

- The work began with real repository activity:
  - reading required instructions
  - inspecting the codebase
  - researching current Codex-specific and Claude-related boundaries
  - making code and documentation changes
- The task was not started in `codex-metrics` at the beginning of that work.
- The bookkeeping happened later, only after the user explicitly asked whether metrics were being tracked.
- The missing step was then corrected by creating:
  - goal `2026-04-02-001`
- That recovered the state, but only after the workflow had already drifted from the intended operating path.

## Root Cause

The failure was not a missing feature in `codex-metrics`.

The root cause was workflow ordering:

- metrics bookkeeping was treated as something that could be added after useful progress existed
- instead of being treated as the first required step once the work had clearly become a real engineering task

This was an execution-discipline problem, not a tooling-capability problem.

## 5 Whys

1. Why was the task not started on time?
   Because implementation and research work began before the bookkeeping step was performed.

2. Why did implementation begin first?
   Because the immediate focus shifted to understanding the architecture and product implications of Claude support.

3. Why did that focus displace bookkeeping?
   Because bookkeeping was treated as recoverable administrative follow-up rather than an up-front workflow invariant.

4. Why was bookkeeping treated as recoverable later?
   Because there was not a strong enough operational guardrail that said task start must happen before substantial work begins.

5. Why does that matter?
   Because delayed bookkeeping weakens the credibility of the dataset and creates exactly the kind of history distortion that this product is supposed to prevent.

## Theory Of Constraints

The constraint was not the CLI.

The real bottleneck was the start-of-task decision loop:

- once substantial work starts
- either bookkeeping has already happened
- or it becomes easy to rationalize doing it later

That means the highest-leverage fix is not better recovery. The highest-leverage fix is a stronger rule on when bookkeeping must happen.

## Retrospective

This incident is small, but it is product-relevant.

`codex-metrics` exists partly to make engineering history trustworthy. If task start bookkeeping slips even inside this repository, then the workflow still has an avoidable failure mode.

The right lesson is narrow and reusable:

- start-task bookkeeping should happen before substantial implementation, documentation, or validation work begins

That is the actual invariant worth codifying.

## Conclusions

- The failure mode was late bookkeeping, not missing bookkeeping forever.
- Late bookkeeping is still a real workflow bug because it weakens timeline trust.
- The correct fix is a reusable workflow guardrail in policy, not just a chat reminder.

## Permanent Changes

- Classification:
  - reusable external policy
- Added an explicit rule to `docs/codex-metrics-policy.md` that task start bookkeeping must happen before substantial implementation, documentation, or validation work begins.
- Kept the packaged policy mirror in sync in `src/codex_metrics/data/bootstrap_codex_metrics_policy.md`.
- No code change was required because the tooling already supports the intended workflow.

