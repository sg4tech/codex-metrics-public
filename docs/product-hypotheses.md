# Product Hypotheses

Use this file to track active product and metrics hypotheses for `codex-metrics`.

Purpose:

- make PM reasoning explicit instead of letting it live only in chat
- separate confirmed product truths from working hypotheses
- preserve why a hypothesis existed, not just the latest opinion
- force periodic re-evaluation when new evidence appears

Rules:

- Treat every non-confirmed product proposal as a hypothesis, not as settled truth.
- For each meaningful hypothesis, record:
  - statement
  - why it matters
  - expected upside
  - main risks or where it may be wrong
  - alternatives considered
  - current confidence
  - evidence status
  - next re-evaluation trigger
- When new evidence appears, update the existing hypothesis entry with a dated note instead of deleting the old reasoning.
- Move ideas into `docs/product-framing.md` only after they are confirmed enough to act as stable framing.
- Keep this file focused on decision-relevant hypotheses, not general brainstorming noise.

## Status Labels

- `active` for current working hypotheses
- `validated` for hypotheses with strong enough evidence to guide default product decisions
- `rejected` for hypotheses that no longer fit the evidence
- `superseded` for hypotheses replaced by a better-framed successor

## Current Hypotheses

### H-001 — Exact outcome fit should be treated as the primary product-quality signal

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - The most decision-useful product metric for `codex-metrics` is closer to exact outcome fit than to raw goal success rate or raw total cost.
- Why it matters:
  - If true, the product should prioritize quality signals such as `result_fit` over top-line closure metrics.
- Expected upside:
  - reduce false confidence from inflated success summaries
  - align reporting with the operator's real pain: "did Codex produce what was actually wanted?"
  - improve evaluation of workflow changes
- Main risks or where this may be wrong:
  - `exact_fit` is operator-judged and may be noisy
  - time-to-acceptable-result may matter more than fit alone
  - a broader acceptance metric may be more useful than strict exact fit
- Alternatives considered:
  - `time to acceptable result` as the north-star metric
  - `rework pressure` as the primary proxy
  - a broader `accepted / accepted-after-rework / not-accepted` model
- Current confidence:
  - `medium`
- Evidence status:
  - supported by this repository's history, where raw success often looked too optimistic and `result_fit` added important truth
  - not yet validated across external projects because their `result_fit` fields are still mostly unreviewed
- Next re-evaluation trigger:
  - after more cross-project reviewed `result_fit` data exists
  - or after a summary redesign is tested against real operator decisions
- Notes:
  - `2026-03-31`: promoted from chat into explicit product hypothesis after repeated concern that success metrics looked too successful.

### H-002 — Retry pressure is likely the strongest secondary metric after quality fit

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - Attempts, failed entries, and continuation chains may be a better second-order operating metric than raw cost.
- Why it matters:
  - If true, summary and audits should highlight rework pressure before aggregate spend.
- Expected upside:
  - improve process decisions around requirements, lead mediation, and guardrails
  - make false "success" patterns easier to spot
- Main risks or where this may be wrong:
  - retry pressure can still miss slow but single-pass bad outcomes
  - some rework is cheap and acceptable, so the metric can overstate pain
- Alternatives considered:
  - speed-first metrics
  - cost-first metrics
  - pure acceptance metrics without retry context
- Current confidence:
  - `medium`
- Evidence status:
  - supported by local history and `audit-history`
  - not yet validated as the best secondary metric across multiple repositories
- Next re-evaluation trigger:
  - after cross-project comparison includes more reviewed quality signals
  - or after speed tracking becomes stronger
- Notes:
  - `2026-03-31`: added during PM review after seeing that retry pressure explained more than raw success in local history.

### H-003 — Raw total cost is a guardrail metric, not the primary north star

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - `Known total cost (USD)` is useful for budget awareness, but it is too coarse to be the main product metric for workflow decisions.
- Why it matters:
  - If true, the product should keep total cost visible but avoid centering product decisions on it.
- Expected upside:
  - reduce over-optimization for cheapness
  - keep quality-first framing intact
  - push analysis toward cost-in-context metrics, such as cost by goal type or by accepted quality outcome
- Main risks or where this may be wrong:
  - in some projects cost may become the dominant business constraint
  - underweighting cost too much could hide profit erosion
- Alternatives considered:
  - total cost as the top-line metric
  - cost per product success
  - cost per exact-fit product goal
- Current confidence:
  - `high` that total cost alone is insufficient
  - `medium` on the best replacement cost view
- Evidence status:
  - supported by current cross-project comparison, where raw totals are not very comparable because goal-type mixes differ substantially
- Next re-evaluation trigger:
  - after cost-by-goal-type or cost-by-quality slices are available
- Notes:
  - `2026-03-31`: derived from comparing `codex-metrics`, `invest`, and `hhsave` snapshots.

### H-004 — Lead-mediated task flow may improve outcome fit by reducing adjacent work

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - Requiring implementation to start from a lead-owned clarified task may increase exact-fit outcomes by reducing scope drift and adjacent technical work.
- Why it matters:
  - If true, process changes around lead mediation are a product lever, not just a team preference.
- Expected upside:
  - fewer “technically strong but not requested” outcomes
  - clearer handoffs from PM intent to implementation
  - lower retry pressure caused by scope drift
- Main risks or where this may be wrong:
  - adds coordination overhead on small tasks
  - can create a lead bottleneck without improving clarity
  - may not matter much when one operator is already disciplined
- Alternatives considered:
  - direct developer execution from raw request
  - lightweight checklist without explicit lead mediation
  - stronger acceptance review only at the end
- Current confidence:
  - `medium-low`
- Evidence status:
  - supported indirectly by repeated local pain around adjacent work and by the new process playbook
  - not yet validated through a tracked pilot on multiple real tasks
- Next re-evaluation trigger:
  - after 2-5 real tasks are run through the playbook manually
- Notes:
  - `2026-03-31`: added after formalizing the reusable process playbook and recognizing that the idea still needs operational validation.

### H-005 — Early PM discovery likely reduces expensive rework more than late technical polishing

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - Clarifying user, JTBD, acceptance criteria, and out-of-scope boundaries before implementation likely reduces rework more than adding more polishing later.
- Why it matters:
  - If true, the highest-leverage product improvement is better pre-implementation clarification, not more downstream checking alone.
- Expected upside:
  - fewer wrong-problem implementations
  - fewer false successes
  - clearer product decisions about what to build next
- Main risks or where this may be wrong:
  - the discovery overhead may be unnecessary on very small obvious tasks
  - some uncertainty only appears after touching the real system
- Alternatives considered:
  - minimal upfront discovery with stronger review later
  - implement-first and clarify through prototypes
  - rely on retrospective correction after misses
- Current confidence:
  - `medium`
- Evidence status:
  - supported by the project's repeated pattern that weak framing created misleading or low-ROI work
  - not yet quantified as a before/after process effect
- Next re-evaluation trigger:
  - after a small batch of manually tracked tasks records whether PM discovery reduced misses or partial fits
- Notes:
  - `2026-03-31`: derived from repeated retros showing that unclear intent hurt more than missing code polish.

### H-006 — Retros with codified follow-up may reduce repeated failure modes more than retros alone

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - Retros are materially more valuable when they end in a classified follow-up such as a test, guardrail, rule, or explicit no-action decision.
- Why it matters:
  - If true, the product and process should treat codified follow-up as the real unit of learning, not the retrospective document by itself.
- Expected upside:
  - repeated failures turn into permanent checks faster
  - less “we wrote it down but nothing changed”
  - clearer distinction between useful and decorative retrospectives
- Main risks or where this may be wrong:
  - can overfit on noisy one-off incidents
  - may push teams to codify weak lessons too aggressively
- Alternatives considered:
  - retrospective logging without required follow-up classification
  - lightweight oral review without docs
  - pure testing focus without retros
- Current confidence:
  - `high`
- Evidence status:
  - strongly supported by this repository's history, where the highest-ROI retros were the ones that became tests, guardrails, AGENTS rules, or workflow changes
- Next re-evaluation trigger:
  - if future retros start creating more noise than lasting improvement
- Notes:
  - `2026-03-31`: added after explicit PM review of which practices actually helped this project.
