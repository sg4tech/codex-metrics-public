# Retrospective: Hypothesis-Driven PM Shift

## Situation

Product discussions in this repository had become more mature, but PM reasoning was still often expressed in chat as if it were a conclusion instead of a hypothesis.

That created a recurring risk:

- a plausible product idea could sound more validated than it really was
- later product shifts could overwrite earlier reasoning without leaving a clean trail
- framing and hypothesis work could blur together

## What Happened

During product analysis around quality, retry pressure, and cost, it became clear that several PM recommendations were still hypotheses:

- whether exact outcome fit is the most useful top-line quality metric
- whether retry pressure is the best secondary metric
- whether total cost should remain a guardrail rather than a north star

Instead of treating these as settled product truth, the workflow was updated to:

- log active hypotheses in `docs/product-hypotheses.md`
- keep `docs/product-framing.md` for the best currently confirmed framing
- require PM proposals in `AGENTS.md` to include upside, risks, alternatives, and confidence

## Root Cause

The repo had already become strong at engineering retros and technical codification, but the product layer lagged behind:

- technical lessons had stable homes
- product reasoning often lived only in chat or in partially confirmed framing docs

So the missing piece was not “more PM thinking.”
It was a stable place and workflow for PM uncertainty.

## 5 Whys

1. Why did PM recommendations risk sounding more final than they were?
   - Because they were often written directly in conversation without a persistent hypothesis record.
2. Why was conversation carrying too much of the product reasoning?
   - Because framing existed, but there was no separate home for active hypotheses.
3. Why did framing absorb some unconfirmed ideas?
   - Because the repo had a place for confirmed product framing but not for intermediate product uncertainty.
4. Why was that gap still present?
   - Because the project matured through engineering rigor first, then added product framing later.
5. Why does that matter now?
   - Because once product decisions start to shape metrics and process, unclear confidence levels become a real product risk rather than just a documentation issue.

## Theory of Constraints

The current bottleneck was not lack of product ideas.

It was lack of explicit hypothesis handling:

- no persistent log for active PM hypotheses
- no default expectation to state confidence and alternatives
- no routine re-evaluation loop after new evidence

Once that bottleneck became visible, adding another metric or polishing the summary more would have optimized the wrong layer.

## Retrospective

What worked:

- separating confirmed framing from active hypotheses
- treating PM recommendations as explicit testable hypotheses
- keeping the new mechanism lightweight instead of creating a heavy PM framework

What did not work well enough before:

- relying on chat memory to preserve product reasoning
- allowing plausible PM statements to sound more validated than they were
- mixing framing and open questions too loosely

## Conclusions

- Product reasoning needs the same explicit uncertainty handling that engineering debugging already gets.
- The right response was not a bigger framework.
- The right response was a narrow artifact and a few operating rules:
  - one hypothesis log
  - one confirmed framing doc
  - one AGENTS rule that PM proposals must be framed as hypotheses until validated

## Permanent Changes

- `docs/product-hypotheses.md` is now the repository's product and metrics hypothesis log.
- `docs/product-framing.md` should hold only the best current confirmed framing, not every plausible idea.
- `AGENTS.md` now requires PM/product proposals to be framed as hypotheses with risks, alternatives, and confidence.
- Meaningful new product or metrics hypotheses should be logged and later re-evaluated instead of silently replacing earlier views.
