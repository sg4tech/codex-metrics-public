# AGENTS vs Policy Boundary Retrospective

## Situation

The bootstrap installer generates two closely related instruction surfaces for downstream repositories:

- a managed `codex-metrics` block inside `AGENTS.md`
- an exported `docs/codex-metrics-policy.md`

Those two surfaces are intentionally not equal. `AGENTS.md` should point agents at the right policy, while the policy should hold the detailed operational contract.

During installer hardening, that boundary drifted again.

## What Happened

The generated `AGENTS.md` block gradually accumulated more than just a pointer:

- command invocation details
- standalone install guidance
- workflow rules
- typical command sequences
- generated artifact handling rules

That made the downstream `AGENTS.md` block look self-sufficient, but it weakened the original design:

- duplicated instructions now lived in both `AGENTS` and policy
- the policy was no longer the obvious single source of truth for behavior
- a new agent could plausibly read only `AGENTS.md` and skip the policy entirely

The user correctly pushed back on this and asked for the boundary to be re-established.

## Root Cause

The installer work kept optimizing for "make the next agent understand this quickly", but without holding a hard enough line on destination layer ownership.

That led to a familiar failure mode:

- useful operational guidance was written
- but it landed in the wrong place

In other words, this was another instance of output-classification drift, this time inside generated downstream repo instructions.

## Retrospective

The right model turned out to be simpler:

- `AGENTS.md` should say "read this policy first"
- the policy should explain what the system is, when it applies, and how to use it

Once that split is respected, both surfaces get better:

- `AGENTS.md` stays small and stable
- the policy becomes the obvious place to improve onboarding and workflow clarity

That also makes regression testing cleaner, because each generated surface has a narrow contract.

## Conclusions

- Generated `AGENTS.md` blocks should stay minimal and reference-oriented.
- Generated policy files should own the operational contract.
- If a new instruction answers "how do I use codex-metrics?", it probably belongs in policy, not in `AGENTS.md`.
- Downstream bootstrap templates need regression tests not just for presence, but for boundary discipline.

## Permanent Changes

- Narrowed the bootstrap-generated `AGENTS.md` block to a `Read first` include/reference contract.
- Moved detailed codex-metrics usage guidance into the exported policy template.
- Added regression assertions that the generated `AGENTS.md` block does not contain workflow commands or generated-artifact handling rules.
- Added policy-onboarding assertions so clarity improvements happen in the policy layer instead of leaking back into `AGENTS.md`.
