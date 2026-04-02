# Model Tracking Retrospective

## Situation

The product hypothesis was to persist the model used for each goal or attempt so the agent can compare quality, retry pressure, and cost by model.

That is a useful product direction, but it also introduces a subtle data-shape problem:

- the attempt history is the source of truth
- the goal summary is only trustworthy when all attached attempts agree
- merges can combine histories that were produced by different models

## What Happened

- Model tracking was added to goals, entries, summaries, and reports.
- The reporting surfaces now expose model coverage and a `by_model` breakdown.
- The merge flow now recomputes the kept goal model from the merged entry history.
- A focused regression test was added for both cases:
  - same model across merged attempts keeps the model
  - different models across merged attempts clear the goal-level model

## Root Cause

The interesting issue was not whether we could store a model name.

The real root cause was provenance ambiguity:

- a closed goal can be clean and single-model
- but after merges, the same goal id can represent mixed-model history
- if we keep a goal-level model in that case, the analytics become misleading

So the implementation had to separate:

- attempt-level truth
- goal-level summary convenience

## 5 Whys

1. Why did we need an extra merge test?
   Because model tracking changes the semantics of the merged history.

2. Why does merge semantics matter here?
   Because merged goals can mix attempts from different models.

3. Why is that a problem?
   Because a goal-level model would falsely imply a single model was responsible.

4. Why not just keep the first or latest model?
   Because that would hide the mixed provenance and distort model comparison.

5. Why does that matter to the product?
   Because the product is supposed to help decide which model is better and cheaper, and false attribution would corrupt that decision.

## QA Demo

The implementation was verified in a way that mirrors product use:

- `pytest` passed for the targeted domain and CLI suites
- `./tools/codex-metrics show` rendered the model coverage section
- `./tools/codex-metrics render-report` produced the markdown report
- merge behavior was checked for both consistent and mixed model histories

For the product demo lens, the key behavior is:

- the tool can now distinguish clean single-model histories from mixed histories
- it can summarize model coverage without pretending the data is cleaner than it really is
- it can surface a `by_model` view for analysis, which is the right starting point for comparing quality and cost

## Retrospective

The implementation landed in the right place:

- attempt history is the source of truth
- goal-level model data is derived only when safe
- mixed-model merges do not pollute the summary with a fake single model

The main product lesson is that model tracking is useful only if it is honest about provenance.

## Conclusions

- This feature is valuable because it makes model comparison possible.
- The important invariant is not “every goal has a model”.
- The important invariant is “every stored model must be trustworthy enough for analysis”.
- When provenance is mixed, the right answer is to surface that uncertainty, not hide it.

## Permanent Changes

- Classification: tests or code guardrails
  - Added regression coverage for merge behavior with same-model and different-model histories.
  - Kept goal-level model derivation conservative in mixed histories.
- Classification: tests or code guardrails
  - Preserved model reporting in CLI and markdown exports so the analysis surface remains visible.
- Classification: retrospective only
  - Use attempt-level model as the primary analytic source when downstream consumers need exact provenance.
