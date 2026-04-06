# GitHub Spec Kit: Deep Dive Research

**Date:** 2026-04-06
**Status:** Research snapshot
**Related:** [AI Dev Workflow Frameworks Overview](./ai-dev-workflow-frameworks.md)

---

## What Is It?

**GitHub Spec Kit** is an open-source toolkit for **Spec-Driven Development (SDD)** — treating specifications as executable artifacts rather than throw-away documentation. Announced by GitHub in September 2025.

**The core problem:** When AI coding agents receive vague prompts ("build me a notification system"), they make plausible but wrong assumptions. Spec Kit forces explicit requirement articulation — *what* users need and *why* — before any code is generated.

**What it is not:** Not an AI agent itself. Not a team simulation (unlike BMAD). Explicitly not waterfall — though critics dispute this.

---

## The 6-Stage Workflow

Sequential and gated: each stage produces an artifact that feeds the next.

### Stage 1 — Constitution (`/speckit.constitution`)
Establishes immutable, non-negotiable project principles (Eight-to-Nine Articles pattern).

**Key articles enforced:**
- Library-First Principle
- CLI Interface Mandate
- Test-First Imperative (TDD mandated)
- Simplicity and Anti-Abstraction (max 3 projects, use frameworks directly)
- Integration-First Testing (real databases over mocks)

**Language rules:** Must use MUST/SHOULD. No vague "should." Lines under 100 chars. Declarative and testable language only.

**Artifacts:** `.specify/memory/constitution.md`, `constitution_update_checklist.md`

---

### Stage 2 — Specify (`/speckit.specify`)
Describes *what* to build — user stories and acceptance criteria. No implementation details.

**Enforced constraint:** "Focus on WHAT users need and WHY. Avoid HOW to implement."

**Explicit uncertainty markers:** `[NEEDS CLARIFICATION: specific question]` placed wherever assumptions would otherwise be made. These flow into the next stage.

**Artifacts:** `specs/[###-feature]/spec.md`, `specs/[###-feature]/requirements.md`

---

### Stage 3 — Clarify (`/speckit.clarify`) — optional but recommended
Agent reads spec, identifies underspecified areas, presents multiple-choice questions (3–5 options per question). Answers are recorded back into the spec before planning begins.

**Why it matters:** Prevents mid-implementation rework by resolving ambiguity before downstream artifacts are generated.

**Artifacts:** Updated `spec.md` with clarifications section.

---

### Stage 4 — Plan (`/speckit.plan`)
Translates spec into technical architecture. User provides tech stack and constraints.

**Two phases:**
- **Phase 0 — Research:** Dispatches research agents on open questions, consolidates into `research.md`
- **Phase 1 — Design & Contracts:** `data-model.md` (entities + TypeScript interfaces), `/contracts/` directory, `quickstart.md`

**Constitution Gates (mandatory):** Simplicity Gate (max 3 projects), Anti-Abstraction Gate (blocks unnecessary wrappers), Integration-First Gate (contracts before implementation code).

**Artifacts:** `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`

---

### Stage 5 — Tasks (`/speckit.tasks`)
Breaks work into numbered, sequenced task list.

**Task conventions:**
- Tasks labeled T001, T002, etc.
- `[P]` markers for parallel execution
- Explicit "Dependencies & Execution Order" section
- Sequencing enforced: contracts → tests → implementation (TDD)

**Artifacts:** `specs/[###-feature]/tasks.md`

---

### Stage 6 — Implement (`/speckit.implement`)
AI executes tasks one by one using `tasks.md` as checklist. Each task has clear definition of done traceable to the spec.

**Post-implementation commands:** `/speckit.critique` (spec quality analysis), `/speckit.analyze` (artifact consistency validation).

---

## Technical Implementation

### Installation
```bash
# Prerequisites: uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install CLI (pin to release tag)
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.1.13

# Initialize project
specify init MyProject
specify init . --ai claude   # for Claude Code

# One-shot (no install)
uvx --from git+https://github.com/github/spec-kit.git@v0.1.13 specify init MyProject
```

### Directory structure created
```
project/
├── .speckit/
│   ├── constitution.md
│   ├── spec.md
│   ├── plan.md
│   ├── tasks.md
│   └── agents.yaml
├── .specify/
│   ├── memory/constitution.md
│   ├── scripts/            # POSIX sh / PowerShell automation
│   └── templates/          # spec, plan, tasks, command templates
├── .claude/
│   └── skills/             # Claude Code slash commands
├── .github/
│   └── prompts/            # GitHub Copilot prompt definitions
├── extensions/
│   ├── catalog.json
│   └── catalog.community.json
└── specs/[###-feature]/
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── contracts/
    └── tasks.md
```

### AI tool integration
Agent-agnostic. Commands are exposed as slash commands per tool:

| Tool | Invocation |
|---|---|
| GitHub Copilot | `/speckit.constitution` |
| Claude Code | `/speckit-constitution` (via `.claude/skills/`) |
| Cursor, Windsurf | Slash commands via rule files |
| Gemini CLI, Codex | Native invocation |

Supported tools (early 2026): GitHub Copilot, Claude Code, Gemini CLI, OpenAI Codex, Cursor, Windsurf, Kiro CLI, Amp, AugmentCode, and ~10 others.

---

## Real-World Usage Feedback

### Positive cases
- Works well for greenfield projects and large enterprise features with well-defined requirements
- Per-task commits with clear traceability to spec artifacts
- Community has contributed 50+ extensions: Jira/Linear/Azure DevOps/Trello integrations, multi-agent QA (MAQA), CI/CD gates, retrospectives

### Critical / mixed cases (from independent evaluations)

**Scott Logic honest evaluation:**
- First feature: 33.5 min agent execution + 3.5 hours review, generating **2,577 lines of markdown**
- Comparable iterative prompting: 8 min + 15 min review
- Plan step alone: 444-line module contract + 395-line data model + 500-line quickstart + 406-line research
- Generated 700-line implementation still had "a small, and very obvious, bug"

**Token cost:** 5x more token usage vs. iterative prompting; users hit Claude Pro hourly limits mid-workflow.

**Cascading regeneration:** Any spec change requires regenerating plan and tasks — described as "super slow."

---

## Limitations and Criticisms

### Structural
- **Waterfall in disguise:** Getting the plan right upfront is critical because changes cascade through all downstream artifacts. This is the exact problem agile was invented to solve.
- **Markdown bloat:** Thousands of lines of markdown that feel redundant and hard to review. Code review may be preferable to spec review for most developers.
- **Misaligned with AI strengths:** Asking agents to write extensive markdown rather than code may be a misuse of models trained on code.
- **No brownfield story:** No clear workflow for existing codebases. Re-running `specify init` can overwrite user-modified files.

### Practical
- **No human-in-the-loop gates between tasks:** Tool allows LLMs to execute all tasks without intervention checkpoints (GitHub Discussion #385).
- **Target audience ambiguity:** Incorporates PM concepts (user stories, feature goals) without clarifying the role split between PM and developer.
- **Problem-size mismatch:** Overkill for medium features; absurd for bug fixes.
- **Maintenance uncertainty:** Primary maintainer (@localden) left Microsoft and joined Anthropic. A maintenance vacuum ensued. Maintenance has resumed (current: v0.1.13) but long-term GitHub organizational commitment is unclear.

### Existential question
Foundation model planning capabilities improve continuously. Whether "a bunch of smart prompts in an open source project" remains competitive against built-in model planning is genuinely uncertain.

---

## Comparison: Spec Kit vs BMAD

| Dimension | GitHub Spec Kit | BMAD Method |
|---|---|---|
| **Core model** | Slash-command toolkit | Multi-agent team simulation |
| **Agents** | One AI doing everything sequentially | 7 specialized personas (Analyst, PM, Architect, PO, Scrum Master, Dev, QA) |
| **Workflow phases** | 6 stages | 4 phases |
| **Context strategy** | Per-feature spec/plan files | Epic sharding to fit LLM context windows |
| **QA** | Extensions/post-impl commands | Dedicated QA persona with traceability matrices |
| **Human-in-loop gates** | Implicit (between stages) | Explicit approval gates |
| **Learning curve** | Lower — a few commands | Steep — 7 personas, YAML config |
| **ROI claims** | Moderate improvement over vibe coding | Claims 55–58% reduction in project hours |
| **Community** | ~39–71k stars*, 50+ extensions | ~19k stars, active Discord, YouTube masterclasses |
| **Maintenance risk** | Primary maintainer transition in progress | Active community |

*Star counts conflict between sources; likely amplified

**When Spec Kit wins:** Teams wanting spec discipline without managing a virtual team. Fast adoption. Already in GitHub ecosystem. Smaller-to-medium projects.

**When BMAD wins:** Large greenfield projects with high ambiguity. Formal QA traceability needed. Team can invest upfront in process.

---

## Key Resources

- GitHub repo: `github.com/github/spec-kit`
- Official docs: `github.github.com/spec-kit`
- Blog announcement: `github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/`
- Scott Logic evaluation: `blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html`
- Martin Fowler SDD tools comparison: `martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html`
- Maintenance status discussion: `github.com/github/spec-kit/discussions/1482`
- BMAD vs Spec Kit comparison: `medium.com/@mariussabaliauskas/a-comparative-analysis-of-ai-agentic-frameworks-bmad-method-vs-github-spec-kit-edd8a9c65c5e`
