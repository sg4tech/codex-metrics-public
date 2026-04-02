# Product Hypotheses

Use this file to track active product and metrics hypotheses for `codex-metrics`.

Purpose:

- make PM reasoning explicit instead of letting it live only in chat
- separate confirmed product truths from working hypotheses
- preserve why a hypothesis existed, not just the latest opinion
- force periodic re-evaluation when new evidence appears
- keep agent-facing analysis assumptions distinct from human-facing conclusion assumptions

Rules:

- Treat every non-confirmed product proposal as a hypothesis, not as settled truth.
- For each meaningful hypothesis, record:
  - statement
  - why it matters
  - expected upside
  - expected resource cost
  - main risks or where it may be wrong
  - alternatives considered
  - current confidence
  - evidence status
  - evaluation plan
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
  - align agent-facing reporting with the real product question: "did Codex produce what was actually wanted?"
  - improve the agent's evaluation of workflow changes
- Main risks or where this may be wrong:
  - `exact_fit` is judged through agent-mediated interpretation and may still be noisy
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
  - or after a summary redesign is tested against real agent decisions and recommendations
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
  - may not matter much when one agent already operates with strong task discipline
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

### H-007 — The generated markdown report may be optional rather than a default artifact

- Status: `active`
- Created: `2026-03-31`
- Statement:
  - For an agent-first product, `docs/codex-metrics.md` may not justify its default generation and commit cost, because structured JSON and CLI output may already provide enough analysis value.
- Why it matters:
  - If true, the product can reduce update noise, token overhead, and duplicate surfaces by making markdown reporting optional or on-demand instead of mandatory.
- Expected upside:
  - reduce duplicated generated output
  - reduce commit noise from report churn
  - keep the main product surfaces focused on agent-readable JSON and CLI output
  - simplify future product evolution by keeping one canonical structured reporting path
- Main risks or where this may be wrong:
  - some agent workflows may still benefit from a compact pre-rendered report
  - markdown may still be useful as a stable snapshot artifact during review or debugging
  - removing the default too early could break habits before agent usage evidence is clear
- Alternatives considered:
  - keep markdown as the current default generated artifact
  - keep markdown but shorten it into a compact summary only
  - keep markdown generation available, but make it explicit or on-demand
- Current confidence:
  - `medium`
- Evidence status:
  - supported by the current agent-first framing, where human direct reading of raw report files is no longer the primary path
  - not yet validated by evidence showing whether agents actually rely on the markdown artifact in practice
- Next re-evaluation trigger:
  - after observing a few more agent analysis cycles on JSON and CLI alone
  - or after testing a json-first, markdown-optional workflow without losing analysis quality
- Notes:
  - `2026-03-31`: added after product review raised the possibility that the markdown artifact is mostly duplicate overhead in an agent-first workflow.
  - `2026-03-31`: converted into a live product experiment by making markdown rendering explicit via `render-report` and `--write-report`, while keeping the hypothesis active until several agent analysis cycles confirm that markdown loss does not hurt synthesis quality.

### H-008 — Separate input, output, and cached-input token tracking may unlock more useful cost optimization than total-token tracking alone

- Status: `active`
- Created: `2026-04-02`
- Statement:
  - Tracking `input_tokens`, `output_tokens`, and `cached_input_tokens` as first-class stored metrics may produce more actionable optimization signals than storing only `tokens_total` and `cost_usd`.
- Why it matters:
  - If true, `codex-metrics` should preserve token-shape data instead of collapsing usage into totals too early, because agent-facing analysis needs to distinguish prompt bloat, response verbosity, and cache efficiency.
- Expected upside:
  - make cost optimization more diagnosis-friendly by separating prompt-side and response-side waste
  - help analyzing agents identify whether a workflow change improved cache reuse or only reduced visible total tokens
  - improve future cost views such as input cost per success, output cost per success, and cached-share by workflow
  - reduce false confidence from total-token summaries that hide materially different token mixes
- Main risks or where this may be wrong:
  - the extra fields may add schema and reporting complexity without materially changing decisions
  - Codex telemetry coverage may be too incomplete or inconsistent for token-shape analysis to be dependable
  - teams may over-optimize output brevity or prompt compression in ways that hurt quality
- Alternatives considered:
  - keep only `tokens_total` and `cost_usd`
  - compute token breakdown ad hoc from raw logs without persisting it in the metrics source of truth
  - expose per-model cost only and leave token-shape analysis out of scope
- Current confidence:
  - `medium-high`
- Evidence status:
  - supported by the current implementation, which already parses `input_tokens`, `output_tokens`, and `cached_input_tokens` for pricing but discards that shape when persisting metrics
  - supported by the product framing that cost should be optimized without hurting quality, which is hard to do well when only blended totals are stored
  - not yet validated by before/after evidence showing that decisions improve once token-shape history is visible in reports
- Next re-evaluation trigger:
  - after the first implementation adds persisted token breakdown fields and at least several real goals are collected with coverage
  - or after analysis shows that separate token-shape metrics do not materially change recommendations compared with `tokens_total` alone
- Notes:
  - `2026-04-02`: added after reviewing current cost tracking and confirming that the CLI already prices input, output, and cached-input separately but the stored metrics only retain rolled-up totals.

### H-009 — Agent-agnostic tracking may create more product leverage than staying Codex-only

- Status: `active`
- Created: `2026-04-02`
- Statement:
  - Extending `codex-metrics` from a Codex-only tracking workflow to an agent-agnostic workflow may increase the product's usefulness more than continuing to optimize only the Codex-specific path, as long as the public CLI contract stays universal across agents.
- Why it matters:
  - If true, the product should evolve toward comparing workflow quality, retry pressure, and economics across multiple agent ecosystems instead of assuming one agent is the only important operating surface.
- Expected upside:
  - increase the number of real repositories and workflows where `codex-metrics` can be used without forcing a Codex-only operating model
  - allow later comparison of outcome quality and retry pressure between Codex and Claude work instead of keeping that difference hidden in notes
  - reduce product lock-in around one telemetry source and make the analysis layer more durable if teams mix agents
  - create a clearer path for future cross-agent cost and quality benchmarking
- Expected resource cost:
  - low-to-medium for the first step, because agent labeling and instruction-file bootstrap support are additive and backward-compatible
  - medium-to-high for full value realization, because reliable Claude usage backfill may require a separate telemetry backend with its own discovery, tests, and maintenance burden
- Main risks or where this may be wrong:
  - the product may become more generic in wording without gaining much real decision value if most serious usage remains Codex-only
  - adding agent labels without reliable non-Codex auto-usage ingestion may create a partially supported workflow that looks more complete than it is
  - cross-agent comparisons may be misleading if model, workflow, and task-type differences dominate more than agent choice itself
- Alternatives considered:
  - stay Codex-only and optimize only the strongest existing telemetry path
  - support multi-agent tracking only through free-form notes instead of internal agent/provider detection
  - delay all generalization until a full Claude telemetry backend is available
- Current confidence:
  - `medium` that first-class agent labeling is worth doing now
  - `low-medium` that full Claude cost/usage ingestion will justify its implementation cost soon
- Evidence status:
  - supported by direct product demand to make the tool work for Claude too
  - supported by the fact that the domain model was already mostly agent-neutral and the first generalization step was cheap and low-risk
  - not yet validated by evidence that teams will actually maintain and analyze a meaningful amount of non-Codex history
- Evaluation plan:
  - measure whether non-Codex work starts appearing in real usage instead of remaining a purely hypothetical capability
  - compare whether the multi-agent extension produces better product decisions, such as clearer workflow recommendations or more useful cross-agent retrospectives
  - compare implementation and maintenance cost against actual new coverage gained:
    - how many goals are later attributable to non-Codex workflows through the universal contract
    - whether those goals produced decision-useful differences in quality, retries, or cost
    - whether lack of Claude auto-usage sync remained a blocker in practice
- Next re-evaluation trigger:
  - after a small but real sample of non-Codex goals exists
  - or when we decide whether to invest in a dedicated Claude telemetry backend
  - or after cross-agent analysis is attempted and we can judge whether the extra surface produced meaningful insight
- Notes:
  - `2026-04-02`: activated after the user explicitly requested making the tool work for Claude too, rather than only for Codex.
  - `2026-04-02`: the product constraint was tightened so the public CLI stays agent-agnostic; generalized instruction-file bootstrap support such as `CLAUDE.md` remains valid, while provider-specific telemetry should stay behind internal adapters.
  - `2026-04-02`: evaluation should treat this as a staged hypothesis, not a fully validated product direction, because the current benefit is broader tracking coverage while the main unresolved cost is a possible Claude telemetry backend.
  - `2026-04-02`: paired with implementation spec `docs/token-breakdown-feature-spec.md` so the hypothesis can be tested through a concrete product increment rather than remaining a vague idea.

### H-010 — Automatic active-task enforcement may improve bookkeeping reliability more than relying on `start-task` discipline alone

- Status: `active`
- Created: `2026-04-02`
- Statement:
  - `codex-metrics` may produce more trustworthy workflow history if it automatically detects started work and enforces or recovers missing task start bookkeeping, instead of depending on the user or agent to remember `start-task` at the right moment.
- Why it matters:
  - If true, the product should evolve from a command-available workflow to a workflow-invariant system, because merely exposing `start-task` does not reliably prevent late bookkeeping.
- Expected upside:
  - reduce late-start bookkeeping incidents that distort task timelines
  - increase trust in `started_at`, attempt sequencing, and retry-history interpretation
  - reduce operator memory burden by shifting bookkeeping from discipline to system support
  - make the product more resilient when agents are focused on implementation rather than process steps
- Expected resource cost:
  - medium for the first implementation, because it requires workflow detection, new invariants, CLI UX decisions, and regression coverage
  - medium-high if later expanded into deeper provider/session-aware recovery
- Main risks or where this may be wrong:
  - aggressive enforcement may create noisy false positives on tiny or exploratory repo edits
  - automatic draft-task creation may create bookkeeping clutter if heuristics are too loose
  - a badly designed guardrail could make the product feel obstructive and encourage bypass behavior
- Alternatives considered:
  - keep relying on `start-task` as a documented command with stronger reminders only
  - add only soft warnings without any enforcement or recovery path
  - defer automation until richer session-aware telemetry is available
- Current confidence:
  - `high` that command availability alone is insufficient
  - `medium` that a worktree-aware guardrail is the right first automation layer
- Evidence status:
  - directly supported by the current repository incident where meaningful work started before task bookkeeping, even though `start-task` already existed
  - supported by the broader product goal that the stored engineering timeline should be trustworthy, not reconstructed late when avoidable
  - not yet validated by before/after evidence showing that automated enforcement materially reduces bookkeeping misses without too much friction
- Evaluation plan:
  - compare the rate of late-bookkeeping incidents before and after the automation
  - observe whether users end up with fewer retroactive bookkeeping recoveries
  - measure whether the first implementation creates too many false-positive warnings or draft tasks
  - judge success by whether the workflow becomes more reliable without making normal use materially more annoying
- Next re-evaluation trigger:
  - after the first implementation of active-task detection and enforcement lands
  - or after several real task cycles show whether the guardrail reduces late bookkeeping
  - or if users start working around the automation instead of following it
- Notes:
  - `2026-04-02`: added after a live incident showed that `start-task` existing as a command was not enough to ensure timely bookkeeping.
  - `2026-04-02`: paired with implementation spec `docs/active-task-enforcement-spec.md` so the hypothesis can be tested through a concrete product increment.
