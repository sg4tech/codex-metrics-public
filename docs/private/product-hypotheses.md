# Product Hypotheses

Index for product and metrics hypotheses in `ai-agents-metrics`.

Working zones:

- `active/` for hypotheses currently being evaluated or actively maintained
- `planned/` for hypotheses that are approved to work on next but not started yet
- `ideas/` for rough candidates that may never become formal hypotheses
- `archive/` for closed, confirmed, rejected, or otherwise retired hypotheses

Read order:

1. Use the map below to open the one file you need.
2. Edit only that hypothesis file.
3. Add short deltas and dated notes instead of rewriting unchanged context.

Writing rules:

- Treat non-confirmed product proposals as hypotheses, not settled truth.
- Keep stable framing in `docs/product-framing.md` only after the idea is confirmed.
- Do not duplicate full hypothesis bodies here; this file is an index only.

Active:

| ID | Status | File | Title |
| --- | --- | --- | --- |
| `H-001` | `active` | `docs/product-hypotheses/H-001.md` | Exact outcome fit should be treated as the primary product-quality signal |
| `H-002` | `active` | `docs/product-hypotheses/H-002.md` | Retry pressure is likely the strongest secondary metric after quality fit |
| `H-003` | `active` | `docs/product-hypotheses/H-003.md` | Raw total cost is a guardrail metric, not the primary north star |
| `H-004` | `active` | `docs/product-hypotheses/H-004.md` | Lead-mediated task flow may improve outcome fit by reducing adjacent work |
| `H-005` | `active` | `docs/product-hypotheses/H-005.md` | Early PM discovery likely reduces expensive rework more than late technical polishing |
| `H-008` | `active` | `docs/product-hypotheses/H-008.md` | Historical conversation analysis may be a better metrics input than live manual tracking |
| `H-009` | `active` | `docs/product-hypotheses/H-009.md` | Separate input, output, and cached-input token tracking may unlock more useful cost optimization than total-token tracking alone |
| `H-010` | `active` | `docs/product-hypotheses/H-010.md` | Agent-agnostic tracking may create more product leverage than staying Codex-only |
| `H-011` | `active` | `docs/product-hypotheses/H-011.md` | A new chat entering an active repository should recover or enforce the active task before mutating work continues |
| `H-015` | `active` | `docs/product-hypotheses/H-015.md` | Retro or meta work may improve product throughput and lower token cost, but current history is too sparse to confirm it |
| `H-016` | `active` | `docs/product-hypotheses/H-016.md` | A structured event-logging layer may be required before we can confidently judge which product changes are actually working |
| `H-017` | `active` | `docs/product-hypotheses/H-017.md` | The product-hypotheses doc should be reorganized around actual decision flow |
| `H-018` | `active` | `docs/product-hypotheses/H-018.md` | Segmented conversation-text analysis may produce better efficiency signals than structural metrics alone |
| `H-019` | `active` | `docs/product-hypotheses/H-019.md` | Higher agent autonomy may improve result quality and lower cost by separating discovery from delivery |
| `H-021` | `active` | `docs/product-hypotheses/H-021.md` | A system-level immutable flag on the metrics file may reduce accidental edits, but it only works with a constrained privileged updater |
| `H-022` | `active` | `docs/product-hypotheses/H-022.md` | A retrospective timeline layer may be required before we can evaluate whether retrospectives improve later product outcomes |
| `H-023` | `confirmed` | `docs/product-hypotheses/H-023.md` | A public-first core with a private overlay may be the safest way to open-source `codex-metrics` without breaking internal iteration |
| `H-024` | `validated` | `docs/product-hypotheses/H-024.md` | The public repository may need generated SEO-ready docs and landing pages from the start to make open-source distribution discoverable |
| `H-025` | `active` | `docs/product-hypotheses/H-025.md` | `bootstrap` may need to become a project starter that can create a new workspace directory and optional non-codex starter setup |
| `H-026` | `active` | `docs/product-hypotheses/H-026.md` | Full-suite automated tests may lower development cost by shrinking the feedback loop and token spend |
| `H-027` | `active` | `docs/product-hypotheses/H-027.md` | Task duration may be required before the revenue side of P&L can be estimated |
| `H-028` | `active` | `docs/product-hypotheses/H-028.md` | Human oversight cost may be a larger hidden expense than AI API cost |
| `H-031` | `active` | `docs/product-hypotheses/H-031.md` | GrowthBook may help measure which features are actually useful or useless by making experiments and feature adoption easier to observe |
| `H-032` | `active` | `docs/product-hypotheses/H-032.md` | Renaming to `ai-agents-metrics` may improve public discoverability and long-term positioning |

Planned:

- none yet

Archived:

| ID | Status | File | Title |
| --- | --- | --- | --- |
| `H-006` | `archived` | `docs/private/product-hypotheses/archive/H-006.md` | Retros with codified follow-up may reduce repeated failure modes more than retros alone |
| `H-007` | `archived` | `docs/private/product-hypotheses/archive/H-007.md` | The generated markdown report may be optional rather than a default artifact |
| `H-012` | `archived` | `docs/private/product-hypotheses/archive/H-012.md` | A `mini-first` model policy may preserve most workflow value at materially lower cost |
| `H-013` | `archived` | `docs/private/product-hypotheses/archive/H-013.md` | Persisting the model used on each goal or attempt may improve quality and cost analysis |
| `H-014` | `archived` | `docs/private/product-hypotheses/archive/H-014.md` | Token consumption speed may be useful only when normalized against product throughput |
| `H-020` | `archived` | `docs/private/product-hypotheses/archive/H-020.md` | Workspace-wide history parsing may be required before cross-project analysis becomes reliable |
| `H-029` | `archived` | `docs/private/product-hypotheses/archive/H-029.md` | A symlink from CLAUDE.md to AGENTS.md may improve rule uptake by putting instructions directly in context |
| `H-030` | `archived` | `docs/private/product-hypotheses/archive/H-030.md` | Event sourcing may eliminate git merge conflicts on the metrics file while preserving history and sync |

Ideas:

- none yet
