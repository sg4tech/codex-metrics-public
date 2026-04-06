# Research: AI-Driven Development Workflow Frameworks

**Date:** 2026-04-06
**Status:** Research snapshot

---

## Context

This document captures a research snapshot of structured AI-assisted development frameworks — starting from BMAD as the entry point, then surveying the broader landscape of alternatives. The goal is to understand which approaches exist, how they compare, and whether any are worth adopting or drawing from in this project.

---

## BMAD Method

**Full name:** Breakthrough Method for Agile AI-Driven Development
**GitHub:** `bmad-code-org/BMAD-METHOD` (~18–20k stars on main repo)
**Docs:** `docs.bmad-method.org`
**Install:** `npx bmad-method install` (requires Node.js 20+, Python 3.10+)

### Core idea

BMAD addresses "vibe coding" — the unstructured, ad-hoc use of LLMs that produces inconsistent results. It replaces improvisation with a structured pipeline of specialized AI agent personas, each scoped to a lifecycle phase. All documentation (PRDs, architecture specs, user stories) is treated as the primary artifact; code is a downstream output.

### 4 Phases

| Phase | Content |
|---|---|
| **Analysis** | Brainstorm, market research, technical feasibility |
| **Planning** | PRD — the only mandatory artifact |
| **Solutioning** | Architecture → epic/story decomposition → readiness validation |
| **Implementation** | Sprint execution: stories → dev → code review |

### Key features

- **12+ agent personas**: PM, Architect, Developer, Product Owner, Scrum Master, QA, DevOps, UX Designer, Tech Writer — each as a YAML/Markdown config file
- **Party Mode**: multiple agents in one session, coordinated by BMad Master — useful for architectural debates and retrospectives
- **3 planning tracks**: Quick Flow (1–15 stories), BMad Method (10–50+ stories), Enterprise (30+ stories)
- **Mandatory phase gates**: cannot proceed to implementation without completed planning artifacts
- **Git as governance layer**: all artifacts versioned in git
- **Tool/model-agnostic**: works with Claude, Cursor, Copilot, any AI coding assistant

### Strengths

- Only framework that combines (a) explicit human approval gates, (b) formal PM/Arch/Dev/QA role separation, and (c) docs-as-primary-artifact
- Methodology, not just tooling
- Free and open source

### Weaknesses

- Relatively niche (18k stars vs 130k+ for LangChain)
- Requires upfront investment in workflow setup
- Better suited for medium-to-large scoped projects; overkill for small fixes

---

## Alternatives Landscape

### Comparison Table (by adoption)

| Framework | GitHub Stars | Core Model | Human Gates | Role/Persona System | Phased Workflow | Model Agnostic |
|---|---|---|---|---|---|---|
| **AutoGPT** | ~183k | Autonomous loop | Minimal | No | No | Partial |
| **LangChain / LangGraph** | ~132k | Graph orchestration | Optional | No | No | Yes |
| **GitHub Copilot** | 20M users | IDE-embedded AI | Yes (review) | No | No | No |
| **Claude Code + CLAUDE.md** | ~85k | Terminal agent + config | Yes | Informal | Informal | Yes |
| **Microsoft AutoGen / MAF** | ~50k | Conversational multi-agent | Native | No | No | Partial |
| **GitHub Spec Kit** | ~50k | Spec-first scaffolding | Yes | No | Yes (6 stages) | Yes |
| **CrewAI** | ~46k | Role-based pipelines | Optional | Yes | Optional | Yes |
| **Aider** | ~42k | Terminal pair programmer | Per-change | No | No | Yes |
| **BMAD Method** | ~18–43k* | Structured agile personas | Explicit gates | Yes | Yes (4 phases) | Yes |
| **OpenAI Agents SDK** | Growing | Lightweight multi-agent | Via guardrails | No | No | OpenAI-centric |
| **Cursor Rules** | N/A (IDE) | Context-injected editing | Implicit | No | No | No (Cursor only) |

### Notable alternatives in detail

#### GitHub Spec Kit
- Official GitHub project (MIT), backed by Microsoft
- 6-stage workflow: Constitution → Specify → Clarify → Plan → Tasks → Implement
- Closest to BMAD's "spec-as-primary-artifact" philosophy
- Works with Copilot, Claude Code, Gemini CLI
- Lacks persona/role separation
- **Detailed research:** [github-spec-kit-deep-dive.md](./github-spec-kit-deep-dive.md)
- **Resources:** `github.com/github/spec-kit`, `speckit.org`

#### CrewAI
- Fully automated role-based pipelines in Python
- 45.9k stars, 100k+ certified devs, Fortune 500 adoption (IBM, NVIDIA, Walmart)
- Raised $18M (Oct 2024)
- Closest technically to BMAD's role model, but removes human gates from the default path
- Requires engineering to configure — not accessible to non-developers
- **Resources:** `github.com/crewaiinc/crewai`

#### LangChain / LangGraph
- Largest ecosystem (130k+ stars, 700+ integrations, 5M weekly PyPI downloads)
- Maximum flexibility — build any agent topology
- LangGraph is production runtime at LinkedIn, Uber, 400+ companies
- No methodology or persona templates — you design everything
- Steep learning curve
- **Resources:** `github.com/langchain-ai/langchain`

#### Claude Code + CLAUDE.md / AGENTS.md
- Lightest-weight alternative: a well-written markdown file that enforces team rules across sessions
- Claude Code: 85k GitHub stars, terminal-native, growing fast
- AGENTS.md is a cross-tool convention readable by Claude Code, Copilot, Gemini CLI, Cursor
- No enforced role separation or phase gates
- **This is what this repository currently uses**
- **Resources:** `code.claude.com/docs`

#### Aider
- 42k stars, terminal-based, model-agnostic, fully git-native
- Every change = a commit; all reversible
- No framework overhead, no roles, no planning phases
- Best for solo developers who want control and cost transparency

#### AutoGPT
- 183k stars — most-starred AI agent project on GitHub (2023 viral growth)
- Evolved toward low-code business automation platform, away from dev coding workflows
- Original autonomous loop known to drift without explicit gates
- Less relevant for structured software development methodology today

---

## Key Takeaways

1. **BMAD is uniquely positioned** as a methodology combining phased workflow + role separation + explicit human gates. No other framework does all three.

2. **By raw adoption**, BMAD is a niche player. The dominant tools are GitHub Copilot (20M users), LangChain (130k stars), and AutoGPT (183k stars, though partially legacy).

3. **The CLAUDE.md/AGENTS.md approach** (what this repo uses) is the lightest-weight option — no infrastructure, just a well-maintained markdown file. Effective when the team discipline is there.

4. **GitHub Spec Kit** is the closest philosophically aligned alternative from a tier-1 vendor (Microsoft/GitHub). Worth watching.

5. **CrewAI** is the most production-validated role-based agent framework, but it's an engineering platform, not a methodology.

6. **For this project's scale**, the current CLAUDE.md/AGENTS.md approach is likely sufficient. BMAD would add value if scope grows to involve multi-role coordination (PM + Architect + Dev as distinct agents on the same project).

---

## Resources

- BMAD: `github.com/bmad-code-org/BMAD-METHOD` | `docs.bmad-method.org`
- GitHub Spec Kit: `github.com/github/spec-kit` | `speckit.org`
- CrewAI: `github.com/crewaiinc/crewai`
- LangChain: `github.com/langchain-ai/langchain`
- Aider: `github.com/Aider-AI/aider` | `aider.chat`
- AutoGPT: `github.com/Significant-Gravitas/AutoGPT`
- OpenAI Agents SDK: `github.com/openai/openai-agents-python`
- Claude Code: `code.claude.com/docs`
