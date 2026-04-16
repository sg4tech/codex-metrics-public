# AGENTS.md

## Repository structure

`oss/` is the primary development directory. All source code, tests, docs, config, scripts, and the canonical `Makefile` and `pyproject.toml` live there. The private root contains only `docs/private/`, `metrics/`, `AGENTS.md`, `tests/private/` (3 files), `.githooks/`, and a thin glue `Makefile` that does `include oss/Makefile`.

Symlinks that make tooling work from the private root:
- `docs/public/` → `oss/docs/`
- `tests/public/` → `oss/tests/`
- `src/` → `oss/src/`

When doing engineering work, prefer working inside `oss/` directly.

## Read first

Before starting any engineering task in a worktree, run `make init` to set up the local Python environment. Do not symlink `.venv` from the main repo — each worktree has its own environment.

In a worktree session, all commits go to the worktree branch. Before any `git add` + `git commit`, verify the current branch with `git branch --show-current`. Never commit to `master` as a side effect of worktree work — only when the user explicitly requests it.

Before starting or continuing any engineering task, run `git pull` to ensure the working branch is up to date, then read:

During a task, run `git pull` again before writing new code if significant time has passed or before starting a new subtask — other agents or the user may have pushed changes in the meantime.

- `AGENTS.md`
- `docs/ai-agents-metrics-policy.md`
- `docs/private/task-lifecycle.md`
- `docs/private/local-linear-setup.md`

The rules in `docs/ai-agents-metrics-policy.md` are mandatory and are part of this repository's operating instructions.

For product-management, framing, and metrics-interpretation work, also read:

- `oss/docs/product-framing.md`
- `docs/private/product-hypotheses.md`
- the relevant `docs/private/product-hypotheses/H-xxx.md` file

For history/search/reconstruction work, also read:

- `docs/public/history-pipeline.md`
- `src/ai_agents_metrics/history_ingest.py`
- `src/ai_agents_metrics/history_normalize.py`
- `src/ai_agents_metrics/history_derive.py`

## Reference documentation

The following docs exist for reference — consult them as needed, not on every task:

- `docs/public/architecture.md` — code structure: modules, pipeline stages, storage, CLI entry points
- `docs/public/data-schema.md` — full field reference for the in-memory data model (GoalRecord, AttemptEntryRecord, summary); storage is `metrics/events.ndjson`
- `docs/public/data-invariants.md` — business rules enforced by validation logic
- `docs/public/glossary.md` — terminology: goal vs task, entry vs attempt, inferred, supersedes chain, EffectiveGoalRecord, etc.
- `docs/public/decisions.md` — why key architectural choices were made
- `docs/public/testing-guide.md` — test structure, conftest.py, factory patterns, common pitfalls
- `docs/public/architecture/README.md` — tracked technical debt (ARCH-001 through ARCH-009)
- `docs/private/public-overlay-sync.md` — operational runbook for syncing between this private repo and the public `oss/` subtree (`make public-overlay-push`, `make public-overlay-pull`, conflict resolution, boundary rules)

## Core working style

- For engineering work, treat Linear as the source of truth for intake and traceability: create or update the relevant Linear issue before writing code, capture the requirements and acceptance criteria there, and work only through that issue.
- Any change to `src/` or `tests/` requires an open metrics goal and a Linear issue. This is a hard gate — not a guideline. It does not matter how the task started (explicit instruction, conversational question, observation). If files in those directories are about to change, intake must happen first.
- For Linear-driven engineering work, use `docs/private/task-lifecycle.md` as the working workflow guide and `docs/private/local-linear-setup.md` as the repo-specific team/status reference.
- Standalone retrospective work is explicitly exempt from the Linear-first intake rule. Log the retrospective in `docs/private/retros/`, track it as `goal_type=retro`, and do not create a Linear issue unless the user explicitly asks to connect it to delivery work.
- Commit subjects for engineering work must match `CODEX-123: summary`; when a change is intentionally not tied to a Linear issue, use the explicit `NO-TASK: summary` prefix instead. Retrospective-only commits must use `NO-TASK: summary`.
- During module splits or structural refactors, preserve the existing import/export surface until a breaking change is explicitly intended and validated.
- Treat shim modules, entrypoints, and re-exported symbols that are exercised by tests or automation as part of the compatibility contract, not as disposable implementation details.
- For workflow and lifecycle changes, prefer an explicit state machine over scattered guard checks; write or update the state/event matrix tests before changing behavior.
- For workflow and lifecycle changes, require explicit closure criteria and a clear handoff path from implementation to review to completion.
- For changes that introduce system-level side effects, reason about the full side-effect surface instead of only the primary artifact; cleanup and verification should cover files, attributes, locks, temp directories, subprocesses, and any other mutated global state.
- For history search or transcript analysis, treat `raw_messages`, `raw_token_usage`, `normalized_messages`, `derived_timeline_events`, and `derived_goals` as the canonical pipeline waypoints before inventing new storage.
- When product framing or success criteria are not yet confirmed by the user, treat drafts as hypotheses, not settled truth.
- When acting as PM, structure proposals explicitly as hypotheses with expected upside, main risks, alternatives, and a confidence level.
- Log meaningful product or metrics hypotheses in `docs/private/product-hypotheses.md` and the matching `docs/private/product-hypotheses/H-xxx.md` file instead of leaving them only in chat.
- Re-evaluate logged hypotheses after new evidence, audits, cross-project comparison, or process changes; update the relevant hypothesis file instead of silently replacing the old view.
- For this product, treat AI agents as the primary consumers of metrics analysis and the human user as the receiver of final synthesized conclusions.
- Do not optimize product framing around a human manually reading raw metrics first when the intended workflow is agent-first analysis and human-facing final output.
- The primary product value is history extraction: point the tool at existing agent history files (`~/.codex`, `~/.claude`) and get insights with no manual setup. Manual tracking (`start-task` / `finish-task`) is an opt-in enhancement layer for explicit goal boundaries and outcome judgements — not a prerequisite for getting value.
- When designing or changing CLI commands, onboarding flows, or bootstrap behavior, orient toward "first run works from history files" as the default success path. Manual instrumentation is a second step.
- Treat agent-agnostic behavior as the default product and API constraint.
- When changing the CLI, bootstrap flow, metrics schema, or reporting contract, prefer one universal agent-facing API over provider-specific user-visible parameters or workflows.
- Keep provider-specific logic behind internal detection or adapter layers unless the user explicitly asks for a provider-specific public surface.
- Before starting implementation, ask all important clarifying questions upfront — resolve ambiguity, constraints, and open decisions before writing any code, so that implementation can proceed without interruptions.
- Write all documentation files in English. This applies to `docs/`, `AGENTS.md`, inline code comments, and any other files committed to the repository. Chat responses to the user may be in any language.
- Treat “adjacent but not requested” output as a primary quality failure, even if the implementation is otherwise technically strong.
- Prefer diagnosis -> guardrail -> verification over clever but weakly defended fixes.
- Keep test-only escape hatches out of production code paths; if tests need to bypass a safety mechanism, prefer dependency injection, monkeypatching, or test fixtures over runtime environment toggles.
- Before investing in more metrics semantics, refactoring, or process polish, ask which layer is the current bottleneck; do not optimize a non-constraint.
- For partial-data metrics, prefer explicit coverage and covered-subset averages over brittle all-or-nothing KPIs that collapse to `n/a`.
- Before writing repetitive boilerplate (copy-pasted fetch functions, near-identical blocks), pause and consider whether extracting a shared helper or compressing the pattern would keep the file within AI context limits (~900 lines / ~10 000 tokens). Files that exceed this limit cannot be read in a single tool call and become expensive to work with.

## Metrics tooling

Do not edit metrics files manually when the updater script can regenerate them.

Use:

`./tools/ai-agents-metrics ...`

Tracked files:
- `metrics/events.ndjson` — append-only event log; the source of truth; tracked in git

Do not edit `metrics/events.ndjson` manually. All mutations must go through the CLI.

For the codex-metrics workflow, goal semantics, reporting invariants, and update/close rules, follow `docs/ai-agents-metrics-policy.md`.
Treat metrics bookkeeping as part of the definition of done for this repository.
Treat metrics from other repositories as read-only inputs for analysis. Never run mutating codex-metrics commands against another project's metrics/report files unless the user explicitly asks for that exact repository to be modified.

## CLI and workflow rules

When editing the CLI or metrics mutation flow:

- preserve CLI behavior unless explicitly asked otherwise
- prefer additive changes over breaking changes
- keep the code simple and readable
- add or update tests together with behavior changes; when a test references a new function, implement the function in the same commit — never leave a test importing a symbol that does not yet exist
- for mutating commands such as `update`, `merge-tasks`, and sync flows, cover three test buckets when practical:
  - happy path
  - invalid-state rejection
  - summary/report consistency after mutation
- do not manually patch generated outputs when the script can regenerate them
- validate inputs strictly
- fail loudly on invalid state instead of silently continuing
- for SQL queries, use proper parameterized placeholders (`?`) for all dynamic values; never build SQL via f-strings or string concatenation with variables — use patterns like `WHERE (? IS NULL OR col = ?)` for optional filters instead of dynamically assembling WHERE clauses
- always use strict typing: prefer concrete types (`NormalizedUsageEventRow`, `GoalRecord`) over `dict[str, Any]` or `Any`; do not suppress type errors with `# type: ignore` — fix the underlying type mismatch instead; in tests, construct properly typed stubs rather than untyped dicts

For repository-initializer or bootstrap-style commands:

- treat them as public-facing initializer flows, not just internal helpers
- design them to support safe reruns and partial existing scaffold states
- separate preflight validation from write execution so conflicts are detected before mutation
- prefer non-destructive failure over partial scaffold writes
- use one canonical wrapped entrypoint for user-facing error handling instead of fixing UX separately per launch surface

For workflow-shaping CLI changes:

- if a new command or command flow is meant to change how agents should work, update `docs/ai-agents-metrics-policy.md` in the same task
- keep the packaged policy mirror in sync with the repo policy
- treat README-only documentation as insufficient for agent-facing workflow changes
- model lifecycle gating as a state machine when a command’s allowed/blocked behavior depends on repository state
- preserve the repair path as distinct from active-work continuation when updating workflow guards

## Validation

After changing the CLI, update flow, bootstrap flow, or metrics semantics:

- run the relevant tests
- run a CLI smoke test
- verify that the workflow appends to `metrics/events.ndjson`

Minimum validation commands:

```bash
python -m pytest tests/public/test_metrics_cli.py
./tools/ai-agents-metrics show
```

Prefer the repository's canonical local validation entrypoint when available:

```bash
make verify-fast   # lint + typecheck + tests (~55s) — use during iteration
make verify        # full suite incl. bandit, pylint, complexity, build-check (~1.5min) — use before committing
```

Local validation reminders:

- after structural refactors, include an entrypoint or compatibility-path check, not just direct module tests
- for bootstrap or initializer commands, validate reruns, partial scaffold states, conflicts, and `--dry-run`
- when running `init` or regeneration smoke checks, prefer temporary metrics/report paths unless the task explicitly targets tracked artifacts
- validate dependent updater flows sequentially, not in parallel
- after any `pyproject.toml` change, `make verify` alone is not sufficient — `make build-check` (included in `verify`) validates that `pip install -e .` succeeds with the current setuptools; this catches PEP 639 violations and similar packaging metadata errors that tests cannot catch

## Git and GitHub safety rules

- **Never** use `--admin`, `--force`, `--no-verify`, or any other flag that bypasses branch protection, required reviews, or CI gates on a shared repository — not for routine work, not to unblock a release, not for any reason — without the user explicitly naming that flag in their instruction.
- **Never** use `git rebase` to incorporate upstream changes into a feature branch. Always use `git merge origin/master` (or the appropriate base branch). Rebase rewrites history and requires a force push, which is disruptive.
- When a merge is blocked by branch policy (`base branch policy prohibits the merge`), **stop and report the block**. Do not retry with elevated flags. Ask the user what they want to do.
- Review approval is a gate set by the user. It is not an obstacle to route around. "Do the release" does not authorize bypassing review requirements.

## Retros Rules

- If the user asks to "сделай ретру" or otherwise requests a retrospective, also log it to a file in `docs/private/retros/`.
- Each notable incident or debugging episode should be stored as a separate markdown file.
- Retros should capture at minimum:
  - situation
  - what happened
  - root cause
  - retrospective
  - conclusions
  - permanent changes
- For significant incidents, prefer using `5 Whys` and `Theory of Constraints` to separate the symptom from the real bottleneck.
- When a retrospective proposes improvements, classify each proposed change before codifying it:
  - local `AGENTS.md`
  - reusable external policy
  - tests or code guardrails
  - retrospective only
  - no action
- Default retrospective follow-up to the narrowest correct scope.
- Do not promote a lesson into reusable policy unless it is genuinely reusable beyond this repository's local development workflow.
- `AGENTS.md` stores project rules; `docs/private/retros/` stores incident history and lessons.
- After a meaningful task is completed successfully and the retrospective is logged, create a git commit for the finished checkpoint.
- Do not create a commit just because lint passed or only a partial technical check succeeded; commit only after the actual task outcome is complete and stabilized.
<!-- ai-agents-metrics:start -->
## Codex Metrics

### Read first

Before starting or continuing any engineering task, always read:

- `AGENTS.md`
- `docs/ai-agents-metrics-policy.md`

Use `tools/ai-agents-metrics ...` in this repository.

If `tools/ai-agents-metrics` is unavailable, stop and report an installation or invocation mismatch before proceeding.

The rules in `docs/ai-agents-metrics-policy.md` are mandatory and are part of this repository's operating instructions.

<!-- ai-agents-metrics:end -->
