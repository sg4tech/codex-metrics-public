# How the Best Companies Work

Signature operating practices from companies that are widely regarded as product-excellent. For each: what they are known for, the signature practice, and what is worth stealing. Not every practice transfers to every context — a two-pizza team in a ten-person startup is two people eating a pizza.

## Contents

- [Amazon](#amazon) — Working Backwards, 6-pager, two-pizza teams
- [Stripe](#stripe) — written memos, craft obsession
- [Apple](#apple) — product review cadence, focus, secrecy
- [Netflix](#netflix) — culture document, context not control
- [Airbnb](#airbnb) — storyboarding, 11-star experience, founder mode
- [Shopify](#shopify) — trust battery, GSD, async-first
- [Linear](#linear) — the Linear Method, small team, opinionated defaults
- [Figma](#figma) — multiplayer as the core primitive
- [Basecamp / 37signals](#basecamp--37signals) — Shape Up, calm company
- [SpaceX / Tesla](#spacex--tesla) — first principles, the 5-step algorithm
- [Y Combinator](#y-combinator) — "make something people want," DTDS
- [Superhuman](#superhuman) — the PMF Engine
- [Intercom](#intercom) — JTBD operationalized
- [Atlassian](#atlassian) — Team Playbook, open by default
- [Google](#google) — OKRs, HEART, dogfooding
- [Anthropic and OpenAI](#anthropic-and-openai) — AI-native operating practices

---

## Amazon

**Known for:** operating at enormous scale with unusually high product standards across disparate businesses.

**Signature practices:**

- **Working Backwards.** Start from the customer experience and write backward to the implementation. The process begins with a **PR-FAQ** — a press release and customer-facing FAQ — written *before* building. If the announcement is not compelling, the product is not ready to be built.
- **6-pager.** Narrative memo, ~6 pages, read silently for the first 20 minutes of a meeting. Replaces slide decks, which obscure weak thinking behind visuals. The writing discipline forces the author to actually think the argument through.
- **Two-pizza teams.** Teams small enough to be fed by two pizzas (roughly 6–10 people). Keeps coordination cost low and ownership clear.
- **Single-threaded leader (STL).** One person fully dedicated to an initiative, not a part-time manager over multiple projects. Eliminates the attention-fragmentation that kills complex efforts.
- **Bar raiser.** In hiring, an independent interviewer from outside the hiring team has veto power. Guards hiring quality against team-level desperation.
- **"Disagree and commit."** Leadership principle that legitimizes acting on a decision one disagrees with, *as long as one has voiced the disagreement first*. Prevents both silent sabotage and endless debate.
- **14 Leadership Principles.** Widely internalized at Amazon, not a poster — real tie-breakers in decisions.

**What to steal:** the 6-pager and PR-FAQ rituals. They are unusually high-leverage and cost nothing to install. The STL model is also worth copying for any initiative that crosses more than two teams.

---

## Stripe

**Known for:** developer-obsessed API-first product, remarkable documentation, "craft" as an operating standard.

**Signature practices:**

- **Writing culture.** Internal memos, written proposals, documented decisions. Writing is treated as the primary thinking tool, not a communication afterthought. The standard is "remarkably clear" — prose that explains the argument in the fewest words that remain accurate.
- **Press-quality craft.** The public surface (docs, API, error messages, dashboards, blog, Stripe Press books) is held to a higher standard than most B2B products. Internal craft standards match.
- **Principled API design.** Stripe has internal documents on API-design philosophy that have shaped the industry (idempotency keys, versioning, error taxonomies). The API itself is a product, maintained with backward compatibility over a decade-plus.
- **Hiring for taste.** Explicit hiring signal for design taste and writing ability across roles, not just designers and writers.

**What to steal:** the writing standard and the idea that the API (or whatever your core surface is) is the product, not an implementation detail.

---

## Apple

**Known for:** tight integration, industry-defining design, unusual focus for a company of its size.

**Signature practices:**

- **Product Reviews (historically with Jobs; now the Executive Review Board).** Senior leadership reviews work at a granular level of detail, directly critiquing design choices. Distinct from empowered-teams orthodoxy.
- **One thing at a time.** Far fewer SKUs than industry norms. When introducing the iPhone in 2007, Jobs explicitly cut three products down to one. The default posture is to say no.
- **Secrecy.** Strict compartmentalization; even senior employees often don't know what adjacent teams are building. Produces sharp launches at the cost of loose internal knowledge-sharing.
- **DRI (Directly Responsible Individual).** Every deliverable has one named DRI. No diffused ownership.
- **Integration across hardware, OS, silicon, apps, services.** Long-term bet that tightly integrated stacks produce better products. Depends on decades of investment to sustain.

**What to steal:** the DRI discipline and the ruthlessness about focus. The detailed senior-leader review is controversial but can be adapted as a "design review with tough critique" ritual.

---

## Netflix

**Known for:** the most-shared corporate culture document in history (over 20 million views), and an unusually crisp operating model.

**Signature practices:**

- **The Culture Document.** Codifies: "freedom and responsibility," "context, not control," "highly aligned, loosely coupled," "no rules rules," "keeper test" (if a team member were to leave, would you fight to keep them? if not, act now).
- **Context, not control.** Leaders set context (strategy, metrics, assumptions) and then let teams make decisions. Minimal process, maximal information-sharing.
- **Informed captains.** For each decision, one person is the "informed captain" who owns it; others input but don't override.
- **Keeper test.** A continuous, explicit check on team quality. Generous severance but low tolerance for mediocrity.
- **No expense policy beyond "act in Netflix's best interest."** Extends the principle from performance reviews into operational policy.

**What to steal:** the informed-captain model; the keeper test as a recurring self-check. Be cautious with "no rules" in environments without Netflix's hiring bar.

---

## Airbnb

**Known for:** design-led product culture, early hospitality-marketplace dynamics, and Brian Chesky's influence on contemporary PM thinking.

**Signature practices:**

- **Storyboarding (from Pixar).** Use storyboarding to design end-to-end user experiences before building. Pixar's head of story trained the Airbnb team.
- **11-star experience exercise.** Imagine what a 5-star experience looks like, then escalate: what would 6-star look like? 7? 11? The absurd extremes surface what matters. Many Airbnb features originated in these exercises.
- **Founder mode (Chesky, 2024).** Explicit rejection of purely empowered-team orthodoxy. Founders should stay deep in details, run skip-levels, operate personally at the level of product decisions that matter. Controversial but influential.
- **Design-led product reviews.** Design shapes the starting question, not just the execution.

**What to steal:** the 11-star exercise is cheap to run and exposes thinking constraints. Storyboarding works anywhere the user journey is non-trivial.

---

## Shopify

**Known for:** merchant-focused product culture, Tobi Lütke's operating principles, and strong async/remote practices.

**Signature practices:**

- **Trust Battery.** Every pair of people has a "trust battery" with each other — full at the start, drained or recharged by interactions. Explicit framing makes trust visible and actionable.
- **GSD (Get Shit Done) framework.** Shopify's internal PM process: a structured way of moving from proposal to prototype to build to release, with clear criteria at each gate.
- **Async-first, writing-heavy.** Pre-pandemic, Shopify leaned into written documentation; post-pandemic, went "digital by default." Meetings are scheduled only when written async doesn't suffice.
- **Chaos Monkey for meetings.** Periodically delete recurring meetings to see if anything breaks. Most don't.
- **Principles over processes.** Tobi has published operating principles publicly; they are referenced in internal decisions.

**What to steal:** the trust battery is a surprisingly useful team-health metaphor. Periodic meeting chaos-monkey is a cheap practice for any team.

---

## Linear

**Known for:** defining what a modern dev-tool operating model looks like. A small team shipping disproportionate impact.

**Signature practices:**

- **The Linear Method** (publicly published, linear.app/method). Principles include: build for the creators (not managers), opinionated software, build for speed, 1-week cycles with explicit scope, keep teams small.
- **Small team, no middle management.** Publicly committed to staying small. Senior engineers and designers do the work rather than manage work.
- **Weekly project cycles.** Short enough to feel urgency, long enough to produce non-trivial work. Cycles end in demos.
- **Craft over scope.** Features are held to a higher polish standard than typical B2B SaaS. Rather than ship mediocre versions of many things, they ship better versions of fewer things.
- **Opinionated defaults.** Strong defaults mean less configuration, which means less cognitive load for users and less surface area for bugs.

**What to steal:** the discipline of opinionated defaults; the craft bar; the 1-week cycle. The "no middle management" model is hard to replicate but worth aspiring to as long as possible.

---

## Figma

**Known for:** reshaping design tools through multiplayer-first architecture and bottom-up enterprise adoption.

**Signature practices:**

- **Multiplayer as the core primitive.** Design collaboration was built in from v1, not bolted on. Changed the industry's default assumption that design tools are single-user.
- **Bottom-up PLG.** Individual designers adopt; teams adopt around them; enterprise follows. Free tier for individuals, education, and prototyping keeps the funnel wide.
- **Community-driven templates and plugins.** User-contributed assets expand the surface without product team effort.
- **Browser-native.** WebGL + WASM bet that paid off; no install friction, always-current versions.

**What to steal:** the lesson that a single foundational architectural choice (multiplayer, browser-native) can be the entire moat. If you're making one of those choices, spend disproportionate time on it.

---

## Basecamp / 37signals

**Known for:** strong opinions on how product and company should be run, formalized into Shape Up and several books.

**Signature practices:**

- **Shape Up.** Fixed time, variable scope. Appetite instead of estimate. 6-week cycles, 2-week cooldowns. Shaped work before the betting table. No backlog grooming. (See `validation-and-shipping.md`.)
- **Calm company.** 40-hour weeks, long weekends, extended vacations. Explicit rejection of hustle culture.
- **Writing as the operating mode.** Pitches (shaped work), weekly updates, Hey-world-style announcements — all written-first.
- **Strong opinions shipped publicly.** DHH and Jason Fried have published dozens of operational opinions through the *Signal v. Noise* blog and books.

**What to steal:** Shape Up in product teams with autonomy; the writing-first operating mode anywhere. The calm-company model works only if the business model supports it.

---

## SpaceX / Tesla

**Known for:** rate-of-iteration far above aerospace and automotive norms, often attributed to Musk's engineering-first operating model.

**Signature practices:**

- **First principles thinking.** Decompose problems to physical/mathematical fundamentals rather than reasoning by analogy. The famous example: reasoning battery costs from commodity metal prices rather than from current battery supplier prices.
- **Musk's 5-step algorithm (from the Starbase tour with Tim Dodd):**
  1. Make requirements less dumb.
  2. Delete the part or process (and add 10% back when needed).
  3. Simplify and optimize.
  4. Accelerate the cycle time.
  5. Automate.
  *Critical order.* Most teams start at step 5 — automating a process that shouldn't exist.
- **Vertical integration.** Manufacture as much of the stack in-house as feasible. Reduces dependency on suppliers' iteration speed.
- **Aggressive timelines.** Publicly commit to dates that are hard. Frequently miss them. The controversy is whether the missed dates are a bug or a feature of the operating model.

**What to steal:** the 5-step algorithm is directly applicable to any engineering or product process. The "delete before you optimize" discipline is especially rare.

---

## Y Combinator

**Known for:** defining startup best-practice orthodoxy through Paul Graham's essays, YC's application and Demo Day cycles, and two decades of accumulated practitioner knowledge.

**Signature practices:**

- **"Make something people want."** The foundational mantra. Printed on early YC t-shirts. All other startup advice is downstream.
- **"Do things that don't scale" (Graham essay).** Early-stage startups should do unscalable things — hand-deliver products, personally onboard every user — because at early scale, manual effort beats premature automation.
- **Weekly office hours.** Founders meet weekly with partners; urgency and cadence embedded in the accelerator model.
- **Focus, iterate, talk to users.** Graham's standard advice collapses to three things. Most founder failures are failures of one of them.
- **Default Alive vs Default Dead (Graham essay).** A startup is default alive if, at its current growth and burn, it will reach profitability before running out of money. Default dead otherwise. Forces clarity on where a company actually is.

**What to steal:** the discipline to keep asking "are you talking to users weekly?" — and the default-alive/default-dead frame as a recurring self-check.

---

## Superhuman

**Known for:** Rahul Vohra's operationalization of Sean Ellis's PMF survey into a repeatable engine.

**Signature practice:**

- **The PMF Engine** (First Round Review, 2018). Systematically measure the % of users who would be "very disappointed" to lose the product. The target threshold is 40%. For users below that, segment to find the best-fit users, double down on what they love, and address what holds back the "somewhat disappointed." The key insight: aggregate PMF numbers hide segment-level clarity — the exercise is segment-then-optimize, not average-then-optimize.

**What to steal:** the entire process, verbatim. One of the cleanest operational translations of a theoretical concept (PMF) into a weekly practice. The First Round essay is freely available.

---

## Intercom

**Known for:** operationalizing Jobs-to-be-Done in B2B SaaS and publishing R&D principles widely.

**Signature practices:**

- **JTBD as the primary framing.** Features, roadmaps, and positioning are framed around the job the customer hires the product to do. Intercom's product team was a major evangelist of JTBD in tech circles.
- **Published R&D principles.** Intercom has shared operational documents like "Intercom on Product" and "Intercom on Jobs-to-be-Done" publicly. The transparency itself is part of the brand.
- **Shipping is the heartbeat of the product.** Visible release cadence, public changelogs, customer-facing release notes.

**What to steal:** the JTBD framing as the default unit of PM conversation ("what job is this feature hired for?"); the discipline of publishing principles publicly as a forcing function on clarity.

---

## Atlassian

**Known for:** developer-tool suite, open-by-default operating culture, and the publicly available Team Playbook.

**Signature practices:**

- **The Team Playbook (atlassian.com/team-playbook).** Dozens of "plays" — structured team exercises for health monitors, working agreements, retrospectives, project kickoffs. Free.
- **Open by default.** Internal documents, roadmaps, decisions tend to be visible company-wide unless there's a reason to restrict. Inverts the default.
- **ShipIt Days.** 24-hour cross-functional hack events, originally inspired by Atlassian's engineering culture. Produces outsized numbers of shipped features.
- **No-commission sales.** Historically sold without a sales team; pricing and product are the sales motion.

**What to steal:** the Team Playbook plays are free, drop-in exercises for teams of any size. ShipIt-style events produce disproportionate creative output at minimal cost.

---

## Google

**Known for:** OKRs at scale, early examples of product analytics discipline (HEART), and historic (if now complicated) innovation culture.

**Signature practices:**

- **OKRs.** Brought to Google by John Doerr from Intel, where Andy Grove had formalized them as MBOs. Quarterly objectives + measurable key results, publicly visible, graded at quarter-end. The discipline is less "use OKRs" and more "use them honestly."
- **HEART framework (Rodden et al.).** Google Research's user-centered metrics framework: Happiness, Engagement, Adoption, Retention, Task success — combined with Goals → Signals → Metrics mapping.
- **Dogfooding.** Engineers use their own products extensively. Maps and Gmail were historically dogfooded heavily.
- **20% time (historical).** Engineers could spend 20% of time on side projects. Produced Gmail and AdSense historically; de facto less so today.
- **Design sprints (Knapp et al.).** 5-day structured sprint to answer a product question via prototyping and user testing. Published in the book *Sprint*.

**What to steal:** OKRs if applied with discipline (and killed if they become ritual). HEART for choosing metrics. The design sprint as a time-boxed discovery tool.

---

## Anthropic and OpenAI

**Known for:** defining operating practices for the frontier AI era. The canon is still forming; much of what they do has not been written up yet.

**Signature practices:**

- **Model cards and system cards.** Standardized public documentation of what a model is, what it's been trained to do, and where its known limits are. Originated in academic research (Mitchell et al., 2019); operationalized by Anthropic and OpenAI for production releases.
- **Responsible Scaling Policy (Anthropic) / Preparedness Framework (OpenAI).** Commitments to evaluate models for dangerous capabilities before deployment, with scaled response thresholds. Formal risk-management for capability growth.
- **Evals-first culture.** Evaluation harnesses are treated as first-class infrastructure. Teams are expected to build evals before building features.
- **Cookbooks and example repos** (github.com/anthropics/anthropic-cookbook, github.com/openai/openai-cookbook). Published operational patterns rather than just API docs. Treat the docs as product.
- **Prompt / system prompt transparency** (Anthropic has published Claude's system prompts publicly). Unusual in the industry and raises the bar for norms.

**What to steal:** the eval-first posture (see `ai-native.md`), model-card-style public documentation for any AI feature you ship, and the principle that cookbooks/cookbook-style docs are part of the product, not a support artifact.
