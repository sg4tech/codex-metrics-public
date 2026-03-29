# 2026-03-29 Zero-Duration Product Window Retro

## Situation

After fixing session-based usage recovery and improving cost audit semantics, the remaining cost coverage tails were no longer broad telemetry failures.

The remaining uncovered product goals were:

- `2026-03-29-097`
- `2026-03-29-100`
- `2026-03-29-101`

They all shared the same pattern:

- `started_at == finished_at`
- no stored cost
- no stored tokens

The audit layer originally surfaced them as `no_usage_data_found`.

## What Happened

We first improved the cost audit so that these goals were no longer misdiagnosed as missing telemetry.

That revealed the real issue more clearly:

- these were not normal closed product windows
- they were bookkeeping windows with zero duration
- automatic usage recovery had almost no chance to find real work inside such boundaries

We then considered a strict rejection rule for zero-duration closed product goals.

That first version was too harsh.
It broke legitimate one-shot product flows and normal result-fit tests because a product goal can be created and closed in one updater call before any cost is explicitly recorded.

The correct solution was to add a small normalization guardrail in the finalize path:

- for closed `product` goals
- when `started_at == finished_at`
- and there is still no stored cost/tokens
- normalize `started_at` to one second earlier

This preserves a non-zero recovery window without inventing a large fake duration and without breaking explicit manual cost/token cases.

## Root Cause

The metrics workflow allowed product goals to be created and closed with a bookkeeping-shaped zero-duration window.

That made downstream cost recovery look weaker than it really was, because the recorded time boundary was too narrow for usage capture.

So the bottleneck was not extractor logic anymore.
It was workflow honesty at goal boundary creation time.

## 5 Whys

1. Why did some product goals still have no cost coverage after recovery fixes?
   Because their recorded goal windows were too narrow for automatic usage capture.

2. Why were the windows too narrow?
   Because `started_at` and `finished_at` ended up equal.

3. Why did that happen?
   Because a product goal could be created and closed in effectively the same bookkeeping instant.

4. Why was that allowed?
   Because the workflow and finalize path treated zero-duration product windows as structurally valid.

5. Why was that a problem?
   Because product goals are used for cost recovery, and a zero-duration boundary does not represent real work time well enough to recover telemetry reliably.

## Theory Of Constraints

Before this fix, it was tempting to continue investigating telemetry coverage.

But the actual constraint had moved.

It was no longer:

- session parsing
- legacy extractor compatibility
- cost reporting semantics

It had become:

- low-fidelity goal boundaries for product work

Once recovery compatibility was fixed, workflow fidelity became the next bottleneck.

## Retrospective

This incident is a good example of a second-order constraint.

At first, missing cost looked like a telemetry problem.
After telemetry compatibility was improved, the remaining misses exposed a workflow problem in how product goals were recorded.

The first attempted guardrail also taught an important lesson:

- rejecting low-fidelity data too early can break valid fast paths

A small normalization in the finalize path was better than a strict reject because it:

- preserved existing user flow
- improved future recoverability
- avoided fake large windows
- stayed reversible and easy to validate

## Conclusions

- zero-duration product windows were degrading future cost recovery
- the remaining issue was workflow fidelity, not extractor failure
- strict rejection was worse UX than bounded normalization
- product goal boundaries need different treatment from meta bookkeeping goals

## Permanent Changes

- closed `product` goals without stored cost/tokens no longer keep a zero-duration window
- finalize-path normalization now shifts `started_at` back by one second when needed
- explicit token/cost cases remain valid and are not normalized away
- cost audit keeps identifying old zero-duration records as `incomplete_goal_window`
- future workflow improvements should focus on recording real product boundaries earlier, not only on better post-hoc recovery
