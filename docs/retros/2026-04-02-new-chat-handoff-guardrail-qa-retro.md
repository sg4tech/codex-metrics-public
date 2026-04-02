# New Chat Handoff Guardrail QA Retrospective

## Situation

The product question was not generic bookkeeping hygiene.

The real target was narrower and more important: when a new chat or fresh agent enters an already-active repository, the system should not let the work continue blindly without first recovering or enforcing the active task.

That is the failure mode we wanted to harden.

## What Happened

We implemented the first protection layer in code instead of only in agent-facing text:

- git-based detection of meaningful started work
- `codex-metrics ensure-active-task` as the recovery path
- strict guardrails on mutating existing-goal flows when work has already started but no active goal exists
- warning output in `show`
- policy updates to keep the agent-facing contract aligned

The result is a workflow that now tries to correct the handoff problem at runtime, not just remind the agent about it.

## Root Cause

The underlying issue was not that agents forgot a paragraph in `AGENTS.md`.

The real bottleneck was that the product needed a code-level invariant:

- if work already exists in the repo
- and no active task is recorded
- the system should force recovery or fail loudly before mutation continues

That is a stronger guarantee than instruction-only guidance.

## QA Product Evaluation

Verdict: pass, with a narrow caveat.

Why this is a good product result:

- it targets the real start-agent failure mode
- it uses repository state instead of provider-specific chat state
- it is agent-agnostic
- it keeps `start-task` as the proactive path while adding recovery and guardrails for late entry
- it is observable and testable through CLI behavior

Why it is not a complete solution:

- it improves the first handoff layer, but it does not remove the need for the agent or wrapper to actually call the recovery command
- it gives us a strong guardrail, not an automatic universal session bootstrap

## Data Sufficiency

We have enough data to judge the direction of the change, but not enough to claim a fully quantified product win.

Enough for:

- a QA-style acceptance verdict
- a directional product call
- detecting false positives, recoveries, and blocked continuations

Not enough for:

- a controlled causal claim about exact reduction rates
- a precise effect-size estimate on fewer late-bookkeeping incidents

So the right future evaluation is to compare:

- recovery count
- blocked continuation count
- false-positive warning count
- number of times a new chat would have drifted without the guardrail

## Conclusions

- The best protection was code-level, not file-level.
- The best first layer was git-based repo-local detection.
- The best recovery path was `ensure-active-task`.
- The best product framing is now the new-chat handoff problem, not generic bookkeeping.

## Permanent Changes

- Classification:
  - reusable external policy
  - tests or code guardrails
  - retrospective only
- Updated the product hypothesis in `docs/product-hypotheses.md` to name the actual target: a fresh chat entering an active repository.
- Kept the policy mirror aligned in `docs/codex-metrics-policy.md` and `src/codex_metrics/data/bootstrap_codex_metrics_policy.md`.
- Preserved the code-level protections already implemented in the CLI and tests.
- Deferred broader guard expansion such as `sync-usage` and `merge-tasks` because the ROI is lower for the specific start-agent problem.
