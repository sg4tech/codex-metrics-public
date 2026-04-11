# Product Framing

This document describes the current best confirmed framing for the product.

Working product and metrics hypotheses that are not yet fully confirmed belong in:

- `docs/product-hypotheses.md` for the index
- `docs/product-hypotheses/H-xxx.md` for the individual hypothesis files

## Product

`ai-agents-metrics` is an internal local agent-facing analysis tool for managing the effectiveness and economics of AI-agent-assisted engineering work.

It is not a general analytics platform and not a public SaaS product.

Current intended category:

- internal agent-facing analysis tool

Current near-term strategic priority:

- ship a public-safe open-source release as fast as practical without breaking the product boundary or publishing internal-only material

## Primary User

The primary user is the AI agent layer that reads metrics, audits history, compares projects, and produces synthesized conclusions about AI-agent-assisted engineering work.

Secondary users:

- the human sponsor who receives the final analysis and decisions later
- future contributors trying to understand why the workflow evolved the way it did

## Job To Be Done

When an AI agent analyzes AI-agent-assisted work, it should be able to manage the effectiveness and economics of that work, and then give the human sponsor the analysis needed to decide what to keep, what to change, and what to investigate next.

Primary external scenario:

- an AI agent reviews a real workflow change in this repository or nearby work
- the agent compares history before and after that change
- the agent explains whether quality, speed, and cost improved
- the human sponsor uses that analysis to decide whether the change should stay, be revised, or be reverted

## Core User Problem

Without this tool:

- it is hard for an agent to tell whether workflow changes create real leverage or just extra activity
- quality, speed, and cost are easy to summarize incorrectly from closure metrics alone
- AI usage cost is easy to underweight or overread without structured context
- retries and failed paths get lost, which makes agent recommendations weaker

The tool exists to make the relationship between outcome quality, delivery effort, and AI cost explicit enough to manage, so the agent can produce grounded analysis instead of a vague metrics recap.

In this framing:

- effectiveness means quality plus speed
- economics means cost, token usage, and waste control

## Confirmed Context So Far

The following product truths are already confirmed:

- the primary user is the AI agent that analyzes the metrics
- the human user is the receiver of final synthesized conclusions, not the main reader of raw metrics
- quality, speed, and cost all matter
- effectiveness means quality and speed together
- economics means cost, token usage, and waste control together
- the product should help decide whether workflow changes actually work and what should be changed again
- the public product contract should stay agent-agnostic by default, even when telemetry or runtime adapters are provider-specific underneath
- the canonical metrics store is the append-only `metrics/events.ndjson` event log, with replayed in-memory state derived at runtime
- fast time-to-public-release is strategically important, so public packaging, repository-boundary safety, onboarding, and discoverability are first-order product concerns for the next phase

The following product questions are still intentionally open and should be treated as active hypotheses until better evidence exists:

- the final best quality metric
- the final best cost metric
- the exact long-term balance between delivery optimization and cost optimization

## Main Workflow

1. Use an AI coding agent such as Codex or Claude to work on a real engineering goal.
2. Record goals, attempts, failures, and cost signals as the work happens.
3. Let an AI agent read goal-level and entry-level metrics together, plus history-derived evidence when it is available.
4. Have the agent produce the analysis needed to judge whether the workflow change improved quality, speed, and cost.
5. Deliver that analysis to the human sponsor rather than raw metric interpretation.

## Core Decisions Supported

The tool should help the analyzing agent answer:

1. Did this workflow change improve quality?
2. Did this workflow change improve speed?
3. Did this workflow change improve cost efficiency enough to matter?
4. Should this workflow change stay, be revised, or be reverted?

## North Star

Primary north star:

- accepted product outcomes with minimal retry pressure and controlled cost

This is not meant to optimize for cheapness alone.

The intended priority order is:

1. quality
2. speed
3. cost control

Cost matters because AI is paid usage and should not eat engineering profit, but cost optimization must not degrade the result.

## Quality Priority

Quality matters most in the analysis, even when speed and cost are also important.

The current practical proxy for quality is:

- how often the result that was wanted is produced without extra corrective passes

In plain terms:

- “got what I wanted right away” is the strongest current signal of quality
- the clearest current symptom of bad quality is “the output is not actually what was requested”

Examples of bad quality for this product:

- adjacent technical work instead of the requested outcome
- partial completion presented as if the goal were solved
- a lot of engineering motion while the core requested result is still missing

These signals should be treated as working proxies, not final truth.

The product is also meant to help discover a better long-term quality metric through real usage history, rather than pretending that the perfect metric is already known.

## Cost Priority

Cost is secondary to outcome quality, but still strategically important.

The desired state is:

- keep AI cost from eating engineering profit
- then progressively reduce token and cost waste without hurting outcomes

So cost should be optimized under a “do not reduce result quality” constraint.

At the moment, the exact best cost-view is still open:

- cost per success
- cost per miss
- cost per attempt
- total cost over time

The system should preserve enough raw cost context to let that be decided later from real use.

## Key Metrics

Current primary metrics:

- product goal success rate
- attempts per closed goal
- entry failure reasons
- known total cost and known total tokens
- model identity on goals and attempts for analysis slices
- history-derived before/after comparisons when available

Current interpretation rule:

- goal-level success must always be read together with entry-level retry pressure and history-derived context
- current quality-related metrics are provisional agent-facing proxies and should be refined empirically over time
- cost is a business signal for how painful success or miss was
- failure reasons are primarily a debugging signal for what the agent should recommend changing next
- external workflow commands and user-facing API should prefer one universal contract across agents rather than diverging per-provider command surfaces

Future direction:

- improve the connection between outcome quality and cost efficiency

## Current Scope

In scope now:

- local append-only event-log source of truth
- optional local markdown export
- goal and attempt history
- retry and failure visibility
- partial automatic usage and cost ingestion from local Codex telemetry
- agent-facing analysis surfaces for retros, verification, and workflow-change analysis
- public-release preparation work that makes the reusable core publishable, understandable, and safe to distribute

Out of scope for now:

- hosted multi-user dashboards
- centralized team analytics
- polished end-user UI
- perfect historical cost completeness

## Product State

Current state:

- internal alpha

That means:

- technically credible
- already useful for internal agent-driven analysis and recommendation loops
- still improving framing, UX, and cost clarity

Current release priority:

- near-term work should prefer the fastest safe path to a public release over lower-leverage internal polish, unless the internal work directly unlocks or de-risks that public release

## One-Month Success

In one month, success should look like:

- the reusable core is publicly releasable without leaking internal-only material
- the public entry surface explains what the product is, how to install it, and why it is useful
- the framing remains stable around agent-first analysis value
- the metrics help an agent decide whether a workflow change improved quality, speed, and cost
- quality signals are trusted more than intuition alone
- cost visibility is good enough to spot obviously wasteful patterns

## One-Quarter Success

In one quarter, success should look like:

- the tool is routinely used by agents to judge real workflow changes
- the resulting analyses can point to concrete workflow changes that improved quality, speed, and cost
- token and cost waste are being reduced without hurting result quality
- the system is helping protect engineering profit, not just describe engineering history
