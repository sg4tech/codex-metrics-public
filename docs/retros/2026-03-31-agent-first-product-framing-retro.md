# Retrospective: Agent-First Product Framing Correction

## Situation

The product framing had improved over time, but it still described the human operator too strongly as the primary user of `codex-metrics`.

That was no longer accurate.

In the actual intended workflow:

- AI agents read the metrics
- AI agents analyze the history
- AI agents produce conclusions and recommendations
- the human sponsor receives the final synthesized result

## What Happened

The framing was corrected in three places:

- `docs/product-framing.md`
- `docs/product-hypotheses.md`
- `AGENTS.md`

The new rule is explicit:

- agents are the primary consumers of metrics analysis
- the human user is the receiver of final conclusions, not the main reader of raw metrics

## Root Cause

The project evolved through several framing stages:

- local bookkeeping script
- operator decision tool
- stronger product and PM framing

But the framing still carried over too much of the earlier “human operator reads the metrics directly” model.

So the error was not missing product thinking.
It was product drift from an earlier stage of the repository.

## 5 Whys

1. Why did the framing drift toward the wrong user?
   - Because earlier product language stayed partially intact after the workflow had already shifted.
2. Why was that dangerous?
   - Because product decisions could start optimizing for the wrong reading experience.
3. Why would that matter in practice?
   - Because summary design, rollout logic, and metric interpretation depend on who the primary consumer is.
4. Why was the mismatch not corrected sooner?
   - Because the repo matured first around metric correctness, then around product usefulness, and only later around agent-centered analysis.
5. Why fix it now?
   - Because once agent-driven analysis becomes the actual usage model, keeping a human-first framing becomes a product-level source of wrong decisions.

## Theory of Constraints

The bottleneck was not data quality or report rendering.

The bottleneck was product identity clarity:

- if the wrong consumer is assumed
- then even correct metrics can be presented and prioritized incorrectly

So the highest-leverage fix was a framing correction, not another reporting or schema change.

## Retrospective

What worked:

- correcting the framing at the product-doc level
- propagating the rule into `AGENTS.md`
- updating the hypothesis language to separate agent-facing analysis from human-facing conclusions

What was wrong before:

- the human sponsor was described too much like the primary user of raw metrics
- some PM reasoning implicitly assumed human-first reading of the summary
- that made rollout and success reasoning easier to misframe

## Conclusions

- `codex-metrics` should be designed first for agent interpretation, not for a human manually reading raw metrics.
- Human-facing value still matters, but it arrives through synthesized analysis, not through direct metric consumption as the primary path.
- Future product decisions should be checked against this question:
  - does this help agents analyze better, or does it only make raw metrics prettier for humans?

## Permanent Changes

- `docs/product-framing.md` now explicitly uses an agent-first user model.
- `docs/product-hypotheses.md` now distinguishes agent-facing analysis assumptions from human-facing conclusion assumptions.
- `AGENTS.md` now states that product framing should optimize for agent-first analysis and human-facing final output.
