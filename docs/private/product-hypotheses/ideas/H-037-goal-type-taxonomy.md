# H-037: Expanding goal_type taxonomy from 3 to 5 types

Status: `deferred`
Created: 2026-04-11
Deferred until: goals count reaches ~50-100

## Hypothesis

Splitting the current `meta` goal_type into `meta`, `debt`, and `ops` may improve analytical signal by separating fundamentally different kinds of non-product work.

## Current state

Three types: `product`, `meta`, `retro`.

`meta` absorbs everything that is not a feature or a retrospective: tech debt (ARCH-xxx), CI/security, packaging, PM discovery, documentation, policy updates.

## Proposed taxonomy

| Type | Semantics |
|---|---|
| `product` | Expands what a user of the tool can do |
| `debt` | Improves code without changing behavior (ARCH-xxx, refactoring) |
| `ops` | CI, security, packaging, infra, deployment |
| `meta` | Policy, docs, audits, PM discovery |
| `retro` | Retrospectives and post-mortems |

## ROI assessment (2026-04-11)

**Verdict: negative ROI at current scale. Deferred.**

Costs:
- Code change is small (~30 min): add 2 values to validation, update policy doc
- Migration: 12 existing goals need reclassification or stay as `meta`
- Cognitive load: choosing from 5 types at every goal_started, boundary cases (`debt` vs `ops`)
- Downstream: HTML report, show command, summary breakdowns need to support new types

Benefits at current scale (~18 tracked goals):
- Statistical breakdowns on groups of 3-5 items produce no actionable signal
- The one user already knows what each goal was by reading its title
- `meta = catch-all` is not a problem at this stage; it reflects the reality that most early work _is_ meta

## When to revisit

- When goals count reaches 50-100 and there is a concrete analytical question (e.g., "how much do we spend on tech debt and does it affect product velocity?") that the current 3-type scheme cannot answer
- When there are multiple users or agents who don't share implicit context about what each goal was

## Notes

- The taxonomy itself is sound; the timing is premature
- If revisited, start with adding `debt` only (highest signal gain per added complexity)
