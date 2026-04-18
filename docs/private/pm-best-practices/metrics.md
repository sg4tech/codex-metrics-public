# Metrics and Analytics

How to measure progress without deceiving yourself.

## Canonical sources

- **Sean Ellis** — the North Star Metric concept; the PMF 40% survey ("How would you feel if you could no longer use this? — very disappointed / somewhat disappointed / not disappointed"). The 40%-very-disappointed threshold is the most widely cited PMF heuristic.
- **Rahul Vohra** — "How Superhuman Built an Engine to Find Product/Market Fit" (First Round Review). Operationalized Ellis's survey into a continuous PMF process.
- **Amplitude** — *The North Star Playbook* (free). Canonical NSM framework: NSM = f(input metrics); guardrail/counter metrics alongside.
- **Alistair Croll / Benjamin Yoskovitz** — *Lean Analytics*. One Metric That Matters (OMTM) per stage of growth; stage-appropriate metrics.
- **Dave McClure** — AARRR "pirate metrics" (Acquisition, Activation, Retention, Referral, Revenue). Dated for B2B but still the ur-funnel.
- **Kerry Rodden et al. (Google)** — HEART framework: Happiness, Engagement, Adoption, Retention, Task success. Goals → Signals → Metrics method.
- **Avinash Kaushik** — *Web Analytics 2.0*. Digital analytics fundamentals; "don't measure, learn."

## Core concepts

- **North Star Metric.** A single leading indicator of long-term customer value. Not revenue (lagging); not activity (too cheap). Good NSMs typically combine breadth × depth × frequency.
- **Input metrics.** 3–5 metrics you believe causally drive the NSM. These are where teams actually act.
- **Guardrail / counter metrics.** Numbers that should *not* move adversely when the NSM moves. Prevents Goodhart's Law gaming.
- **Leading vs lagging.** Leading indicators move first and are actionable; lagging indicators confirm but arrive too late to intervene.
- **PMF survey (Ellis/Vohra).** Recurring survey of engaged users; track the 40% threshold by segment. Segments below 40% reveal positioning leaks.
- **HEART.** Pick among Happiness / Engagement / Adoption / Retention / Task-success per product or feature; don't use all five for everything.
- **OMTM per stage.** Different business stages (empathy → stickiness → virality → revenue → scale) have different constraining metrics.

## Practical principles

- **Own one number.** A PM without a primary metric is a project manager.
- **Activity metrics are not outcome metrics.** "Launched four features" is output. "30% of new users reached aha moment in week 1" is outcome.
- **Ratios and rates over raw counts** once past earliest stage. Raw counts hide dilution and churn.
- **Segment first, aggregate second.** Aggregate PMF scores can be 35% while the best-fit segment is at 65%.
- **Counter-metric every KPI.** Every metric gameable without a guardrail will eventually be gamed, including accidentally.
- **Define `n/a` policy explicitly.** For partial-coverage metrics, either report covered-subset averages with coverage %, or the metric collapses under noise.
