# Product Strategy — ai-agents-metrics

**Last updated:** 2026-04-18
**Status:** initial strategic framing, pre-execution. Founder has not yet picked the thesis. Execution Week 1 is waiting on thesis selection + live data export.

This document captures the product strategy agreed between the founder (Viktor) and the embedded-PM role. It is the source of truth for GTM and positioning decisions on this project. Update it when the strategy evolves, do not silently replace.

---

## 1. Goal

- **Primary:** reputation. The project is a vehicle for personal brand in the AI-dev space through thought leadership.
- **Secondary:** validation — evidence that the tool is useful to people other than the author.
- **Out of scope:** monetization. The project is OSS forever; no commercial plans attached to this tool.

"Success" is *not* raw download counts or GitHub stars as vanity metrics.

Success is:
- Authoritative voices in the AI-dev space citing, quoting, or referencing the project or its POV (Simon Willison, Swyx, Anthropic/OpenAI DevRel, a16z AI orbit, etc.)
- 500 highly-qualified stars (AI engineers, tool-builders, tech leads) >> 5000 hype stars
- At least one public cite of a framework (e.g., "retry rate") by a recognized voice

---

## 2. Founder context (as of 2026-04-18)

- ~1 month of active daily work on the project
- Technically credible core: history extraction pipeline validated (H-008)
- Energy and ideation have dropped; bottleneck has shifted from "build" to "product direction"
- Ready to re-invest if external signal confirms value
- Willing to do personal outreach, public posting, thread/post writing under own name
- Authorized **embedded-PM mode**: PM drafts README, posts, outreach messages; founder reviews and publishes

Implication for strategy: external feedback loop must start *fast*, because the primary risk to the project is not technical, it is founder attrition.

---

## 3. Diagnosis (Rumelt kernel)

Honest reading of the current reality that shapes what we should do:

1. **Market timing is favorable.** 2026 is when mass-market awareness of "AI-tool ROI" is moving from early adopters into early majority. The window exists but is not permanent.

2. **Product-distribution mismatch.** The product is agent-first (primary consumer = an AI agent). But reputation and stars come from humans, who share *visual, shareable artifacts*. CLI tables rarely qualify. A human-facing hero artifact is required.

3. **Category vacuum.** There is no settled category name. Without a category, discovery is hard (Dunford). A category must be picked and owned before any broader distribution push.

4. **Bottleneck is not features.** 18 active hypotheses. By Theory of Constraints, optimizing the feature pipeline further right now is non-constraint work. Real constraints in priority order: (a) founder energy / external feedback loop, (b) thesis articulation, (c) hero-artifact quality, (d) positioning clarity.

5. **Counter-positioning opportunity exists.** Local-first + multi-agent + no cloud, against LangSmith/Langfuse (which target build-with-AI, not use-of-AI) and Cursor/Copilot analytics (single-vendor). Defensible on privacy angle.

6. **"Hair on fire" segment exists and is growing.** Devs paying for 2+ AI coding subscriptions, increasingly questioning ROI; tech leads justifying team budgets of $1–5k/month to skeptical stakeholders.

---

## 4. The bet

> Become the default way a developer sees what their AI agents actually do — one visual command that, in 30 seconds against existing history, shows cost, retry rate, and outcome fit. Local, private, multi-agent. Framed by a publicly-defended point of view on AI-tool ROI.

**Explicit non-goals (for now) — what the strategy says no to:**

- Hosted dashboards
- Team-level analytics
- CI / team-tool integration
- Web UI with auth
- Competing with LangSmith / Langfuse on their field

These may return later. They are not first-mile.

---

## 5. Positioning (Dunford's five components)

| Component | Current answer |
|---|---|
| Competitive alternatives | Doing nothing; ad-hoc cost tracking in provider dashboards (Anthropic/OpenAI usage); vendor-specific analytics (Cursor, Copilot); manual spreadsheets |
| Unique attributes | Multi-agent support; local execution; reads existing history with no setup; structured goal/attempt extraction from unstructured chat |
| Value | "Know whether your AI tools are helping or just burning tokens." |
| Best-fit customer | Solo dev or tech lead, uses ≥2 AI coding agents heavily, pays personally or approves a team budget |
| Market category | **Working candidate:** "AI coding-agent analytics" or "personal AI-usage telemetry" — pick one and own it |

**Open decision:** which category label to own. Must be resolved before public launch.

---

## 6. Thesis candidates

A reputation-first strategy requires **one publicly-defended point of view**. The product is proof-of-work under that POV, not the other way around. Candidates seeded from the existing hypothesis catalog:

- **A) "Your AI budget isn't the API — it's your own attention."** (Derived from H-028: human oversight cost > AI API cost.) Counter-intuitive, viral-shaped, requires clean data showing human oversight cost > API cost.
- **B) "Retry rate is the AI-tool metric everyone is missing."** (Derived from H-002.) Framework-level opinion, easy to defend, easy to argue against.
- **C) "Most of your AI spend goes to 3 measurable failure modes."** (Derived from H-001 + failure taxonomy.) Practical, actionable, shareable.
- **D) Founder's own surprise finding.** Whatever, after 30 days of tool usage on own data, was the most surprising or opinion-changing signal. Often stronger than pre-specified candidates.

**PM's current favorite:** A — most counter-intuitive, highest viral potential, reframes an existing narrative rather than adding to it. But should be confirmed against real data before lock-in.

**Decision owner:** founder. Decision blocked on: live tool output review (see Section 9).

---

## 7. Four-week execution plan

Appetite-driven (Shape Up), not estimate-driven. Dates not committed; order and kill criteria are.

### Week 1 — thesis lock + hero artifact

- Pick the thesis from A/B/C/D
- Ship the HTML-report hero artifact on founder's own 30 days of data
- **Kill criterion:** if by the end of the week the resulting screenshot is not something the founder would personally retweet → the product is not ready. Return to shaping. Do not proceed.

### Week 2 — first 3 external users, draft post

- Put the tool in the hands of 3 known devs who use AI agents actively
- Collect their reactions (with permission, for the post)
- Write a draft post in the format: "I analyzed 30 days of my AI coding across Claude/Codex. Here's what I found + the tool I built."
- Share the draft privately with 2 trusted critics

### Week 3 — public POV launch

- Publish the thread/post on the founder's main platform (Twitter/blog)
- Three personal DMs: Simon Willison, Swyx, one Anthropic/OpenAI DevRel
- Reddit post in r/ClaudeAI in the "I analyzed and found X" format (not "I built a tool")
- **Explicitly no Show HN yet.** HN is a one-shot; wait for social proof.

### Week 4 — measurement and decision

- Count: real external users, qualified reactions, cited-by instances
- Mini PMF survey of the earliest users (Ellis 40% frame)
- **Kill criterion:** if <3 real external users or zero qualified reactions → stop and re-form the POV. Do not double down on another channel.

---

## 8. Distribution channels (priority order)

1. GitHub README as landing — animated GIF in the first 30 lines, tagline, one-line install, one-line value prop
2. Founder's Twitter/X — their own audience
3. Targeted DMs — Simon Willison, Swyx, one Anthropic/OpenAI DevRel
4. Reddit r/ClaudeAI, r/LocalLLaMA — analysis-post format, not promo
5. **Show HN** — *later*, after some proof
6. AI-dev newsletters — TLDR AI, Ben's Bites, Latent Space, Pragmatic Engineer
7. YouTube dev-AI influencers — Matthew Berman, AI Jason
8. `awesome-*` lists — awesome-claude, awesome-llm-apps

---

## 9. Open decisions / what is waiting on the founder

1. **Thesis pick (A/B/C/D).** Primary unblock. All execution depends on this.
2. **Export live tool output on founder's own 30 days of data** to a readable file the PM can review — informs thesis selection and extracts candidate insights for the post. PM will not speculate on a thesis without seeing real data.
3. **Confirm category wording:** "AI coding-agent analytics" vs "personal AI-usage telemetry" vs other.
4. **Embedded-PM scope is confirmed** (founder said yes): PM drafts README, posts, outreach messages; founder reviews and publishes under own name.
5. **Weekly check-in on founder energy** — opt-in agreed in principle; to confirm at next session start.

---

## 10. What would change this strategy

Re-open the whole plan if:
- Primary goal changes (e.g., monetization becomes real)
- A competing tool ships a similar hero artifact first
- After Week 4, external reaction is genuinely silent — implies POV or product isn't yet right
- Founder energy does not recover even with external feedback — that's a signal about the project, not the strategy

---

---

## Amendment — 2026-04-18 (later same day)

After founder review of the initial strategy above, the diagnosis shifted. The founder's honest report: after ~1 month of daily use, the tool has **not produced a meaningful insight for its own primary user** (the founder). The one genuine learning of the month — that cheaper models give subjectively similar quality at much lower cost — was not derived from the tool; it came from direct experimentation.

This inverts the priority. The earlier framing ("product is technically credible, bottleneck is distribution") is wrong. Real state: **the tool does not currently answer questions that arise in the user's real work**. Reputation distribution on top of weak PMF is a trap; shipping to influential voices with a raw tool damages brand rather than building it.

### Revised immediate next step

Before any thesis lock or launch activity: **diagnose the gap between what the tool outputs and what the founder actually wants to know.** Concretely:

1. Founder runs the tool on their own 30 days of data, exports the richest available report
2. PM reviews the output + a list of questions the founder actually had during the month
3. From that we decide between three paths (surfaced during the session):
   - **Path A — narrow pivot.** Kill most of the current surface, ship one narrow thing the founder would use daily (candidate: "which of my tasks actually need the expensive model?").
   - **Path B — reframe as learning artifact.** Keep the tool as illustration; center the brand on the public learning curve of building it (Willison/Karpathy model).
   - **Path C — sunset.** After a month without insight for the author, accept the hypothesis did not hold; take the skills, drop the project.

### What we paused

The four-week GTM plan in Section 7 is on hold until the gap is diagnosed. No outreach, no Show HN, no public POV launch with a raw tool.

### Distribution status

Founder confirmed there are specific people ready to receive the tool, but does not yet know what to tell them. This is a positioning/pitch gap that is downstream of the insight gap — you cannot pitch value you cannot yourself articulate from your own usage.

---

---

## Amendment — 2026-04-18 (final lock for this session)

After the gap diagnosis above, the founder made the terminal set of decisions that close open questions in Sections 4–9. These are not hypotheses; they are locked until explicitly revisited.

### Locked decisions

1. **Product thesis (replaces Section 6 candidates A/B/C/D):** the tool exists to answer **"which AI-collaboration practices statistically correlate with better outcomes for this user"** — personal A/B testing of AI workflow (retrospectives, QA-pass, code review, model choice, etc.). Opening question: *"do retrospectives actually help?"*. Candidate A (attention-cost), B (retry rate), C (failure modes) are deprecated; they may return later as derivative narratives under this thesis.

2. **Practice-tagging mechanism (Option B):** practices are detected by an LLM classifier over normalized session messages. **The founder will not hand-tag anything, ever.** Any product path that requires human classification is rejected on arrival.

3. **Manual-tracking layer (supersedes H-011, H-016, H-022, confirms H-036):**
   - `events.ndjson` is **retained** as the tool's internal self-observation log (agent dogfood).
   - `start-task` / `finish-task` / `update` are **not product features**. They exist only as agent-internal workflow gates inside this repo.
   - **No user-facing reports or graphs are built on top of `events.ndjson`.** All user-facing analytics come from the history pipeline (warehouse) plus the practice classifier.

4. **Primary agents:** Claude Code + Codex, both. Agent-agnostic support is not optional — it is the default (H-010 confirmed behaviorally).

5. **User-visible deliverables the founder wants (not ranked):**
   - Beautiful cost/usage graphs sliced by project
   - Ability to ask the tool deeper questions about past work ("did retros help?")

### What this invalidates

- The four-week GTM plan in Section 7 remains paused. No launch activity until the tool produces at least one practice-effectiveness finding the founder would personally share.
- "Hero artifact" (Section 7, Week 1) is redefined from "HTML report the founder would retweet" to "one slicing that answers a practice-effectiveness question with visible statistical caveats."
- Week 1 investigation scope (current): fix/document history-extraction pipeline so warehouse numbers are trustworthy before a practice classifier is built on top of unreliable base metrics.

### Known-broken in base metrics (2026-04-18)

Preliminary audit of `src/ai_agents_metrics/history/` found four concerns the founder flagged plus one critical bug:

1. Goal/attempt heuristic is trivial (1 session-file = 1 attempt, 1 thread = 1 goal; no semantic understanding). Works but opaque — needs plain-language explainer.
2. `failure_reason` is dead-wired in the warehouse (no column; populated only via manual `finish-task fail`). Under Option B this becomes an LLM-classifier output.
3. **[CRITICAL] `derive_insert.py:247–251` — project-level token aggregation silently treats missing token data as 0**, deflating per-thread averages without surfacing coverage gaps.
4. Multi-model sessions (Claude + Codex mixed) are collapsed to a single "dominant" model with lexicographic tiebreaker — cost misattribution risk on this user's primary workflow.
5. No warehouse-level cost field; cost computed separately in `usage_backends.py` from pricing tables, stored only in NDJSON. Cost numbers in reports are one abstraction removed from audit.

Full audit to be written up in `docs/private/extraction-explained.md`.

---

## Related docs

- `oss/docs/product-framing.md` — product definition, JTBD, primary-user model
- `docs/private/product-hypotheses.md` — active hypotheses index
- `docs/private/product-hypotheses/H-001.md`, `H-002.md`, `H-028.md` — hypotheses underlying the thesis candidates
- `docs/private/pm-best-practices/` — external PM canon (reference only, not project-specific)
