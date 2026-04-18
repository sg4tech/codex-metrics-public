# AI-Native Product Management

Patterns for products where the core behavior is produced by a model, not deterministic code. The field is young and moving fast; canon is still forming. Treat this file as a snapshot, not a finished reference.

## Canonical sources

### People and blogs

- **Hamel Husain** (hamel.dev) — "Your AI Product Needs Evals" is the foundational essay on eval-driven development for LLM products. Argues evals are to AI products what unit tests are to software. Also strong on consulting patterns and data-viewing discipline.
- **Shreya Shankar** (sh-reya.com) — research papers and blog posts on eval methodology, including "Who Validates the Validators?" and work on LLM-as-judge calibration.
- **Eugene Yan** (eugeneyan.com) — applied ML patterns, production LLM systems, retrieval, eval design. His "Task-specific LLM evals" and "Patterns for Building LLM-based Systems" posts are widely referenced.
- **Jason Liu** (jxnl.co, author of the `instructor` library) — eval-driven consulting practice; strong opinions on when structured output helps and how to run AI consulting engagements.
- **Simon Willison** (simonwillison.net) — running commentary on LLM tooling; the best single feed for practitioner-level observation. Originated the prompt-injection discussion.
- **Chip Huyen** — *Designing Machine Learning Systems* (pre-LLM canon), *AI Engineering* (LLM-era). The closest thing to a textbook.
- **Andrej Karpathy** (YouTube, Twitter) — public-facing explanations of how LLMs actually work, highly influential on intuition-building.
- **Andrew Ng** — practical AI engineering through DeepLearning.AI courses; "AI Fund" perspective on applied AI businesses.
- **Lilian Weng** (lilianweng.github.io) — deep technical surveys of LLM agent design, prompt engineering, hallucination.

### Labs and tooling

- **Anthropic cookbooks** (github.com/anthropics/anthropic-cookbook) and **OpenAI cookbook** (github.com/openai/openai-cookbook) — official patterns from the labs.
- **Anthropic's "Building effective agents"** (anthropic.com blog) — clear taxonomy of workflows vs agents, and when each is appropriate.
- **a16z infra posts** — strategic/market view of the LLM stack.

---

## Core patterns

### Evaluation

- **Eval-driven development.** Every hypothesis about model behavior becomes an eval. Evals are versioned, run on CI-like cadence, and block shipping when they regress. If there is no eval for a claim, the claim is not operational.
- **Golden datasets.** Hand-curated sets of representative inputs with known desired outputs. Expensive to build. The single most valuable asset in an AI product — and the one most teams under-invest in.
- **Eval categories** (ordered from cheapest/fastest to most rigorous):
  1. **Assertion-based** — regex, JSON-schema validation, format checks. Free. Catches gross failures only.
  2. **Reference-based** — exact match, BLEU, ROUGE, embedding similarity against a gold answer. Cheap. Works only when there is a defensible reference.
  3. **LLM-as-judge** — a stronger model rates outputs. Fast and scalable, but requires calibration against human judgment on a sample, or you are optimizing a proxy.
  4. **Human eval** — slow, expensive, the ground truth. Reserved for calibration and high-stakes releases.
- **Rubrics over scores.** A rubric with 3–5 explicit criteria produces more useful judgments than a single numeric score. Scores average away the signal.
- **Failure taxonomies.** When a model fails, categorize why: hallucination, instruction-following, retrieval miss, reasoning error, formatting, refusal, safety-false-positive. The taxonomy drives where to invest.
- **Offline evals vs online evals.** Offline evals run against golden datasets. Online evals run against production traffic samples. Both are needed; neither substitutes for the other.

### Retrieval and RAG

- **Retrieval quality is usually the bottleneck, not generation.** A better model on top of poor retrieval produces confident wrong answers.
- **Retrieval metrics.** Recall@k and precision@k on a golden question-to-chunk set. If retrieval recall is low, no prompt engineering fixes it.
- **Chunking strategy matters.** Fixed-size chunks with overlap is the default; hierarchical, semantic, or document-structure-aware chunking often helps.
- **Hybrid retrieval.** Dense (embedding) + sparse (BM25) retrieval often outperforms either alone. Re-ranking with a cross-encoder further improves precision at the cost of latency.

### Agents and workflows

- **Workflows vs agents (Anthropic framing).** Workflows = predefined chains of LLM calls with deterministic control flow. Agents = dynamic, model-driven control flow. Workflows are more reliable, easier to debug, and sufficient for most use cases. Reach for agents only when the task actually requires open-ended planning.
- **Error compounding.** A 90% reliable single step becomes 59% reliable after five sequential steps. Multi-step systems multiply individual step reliability; aim for high-90s per step before chaining.
- **Tool use and structured output.** Function calling / structured output reduces brittleness compared with free-text parsing. JSON schemas or typed output make downstream code easier and errors louder.
- **Agent observability.** Every step in an agent loop must be logged: input, output, tool calls, tokens, cost, latency. Debugging agents without traces is impossible at scale.

### Prompts and context

- **Prompt versioning.** Treat prompts like code: diffed, reviewed, linked to evals. A prompt change without an eval run is a silent regression risk.
- **Prompt engineering as a second-order skill.** Below the level of model choice and retrieval quality; above the level of hyperparameter tuning. Often over-invested in early and under-maintained later.
- **Context management.** Long-context models shift the failure mode from "what can fit" to "what should fit." More context is not always better — irrelevant context degrades attention.
- **System prompt design.** System prompts that specify role, constraints, examples, and refusal conditions produce more predictable behavior than terse ones. Anthropic has published Claude's system prompts publicly as a reference point.

### Cost, latency, and economics

- **Token economics as first-class.** Cost-per-outcome, not cost-per-call. Cost appears in product design decisions, not just finance reports.
- **Model tiering.** Use cheap, fast models for routing, summarization, and pre-filtering; reserve expensive models for tasks that need them. A well-tiered system can cost 10× less than a single-model design at equal quality.
- **Caching.** Prompt caching (Anthropic) and KV caching reduce both cost and latency for repeated prompt prefixes. Designing prompts with cache-friendly prefix structure is worth the effort.
- **Batching and streaming.** Batch requests for throughput, stream for perceived latency. Different UX implications.
- **Latency SLOs.** Set p50 and p95 latency targets. AI products degrade on latency faster than users articulate.

### Deployment and observability

- **Traces, spans, token logs.** Tools: LangSmith, Phoenix (Arize), Langfuse, Braintrust, Helicone, Weights & Biases Prompts. The *absence* of observability is the default failure mode.
- **Shadow mode / canary.** Run a new prompt or model on a slice of traffic, log outputs, compare against production without exposing users. Essential for non-trivial changes.
- **A/B testing with calibration.** Classical A/B testing applies but requires larger samples when outcomes are noisy (as AI outputs often are). Pre-register the primary metric and the sample size.
- **Model drift monitoring.** Model providers ship updates; behavior on your pipeline changes silently. Periodic re-runs of evals on production traffic samples catch drift. Subscribe to provider changelog RSS feeds.

### Human-in-the-loop

- **Override as a metric.** % turns requiring human override, time-to-override, override category. Autonomy is a measurable product property.
- **Confidence-gated autonomy.** The model acts autonomously when confident; defers to a human otherwise. Requires a calibrated confidence signal (hard).
- **Feedback capture.** Collect user feedback (thumbs up/down, corrections) and route it back into evals and fine-tuning datasets. The feedback pipeline is itself a product.

### Safety and trust

- **Model cards and system cards.** Public documentation of what the model is, what it's been trained to do, known limits. Originated in academic research; now industry norm for production releases.
- **Prompt injection.** Treat user input and tool-returned content as untrusted. Separate trust levels across prompt regions. Simon Willison's writing is the clearest reference.
- **Hallucination containment.** Constrain generation to retrieved sources (RAG with citation). Detect ungrounded claims. Expose sources to users.
- **Refusal vs safety balance.** Over-refusal is a failure mode — measure false-positive refusals alongside false-negative harms.

---

## Common failure modes

- **Evaluating only on happy-path inputs.** Production distribution has long tails; evals that ignore them miss 80% of real failures.
- **LLM-as-judge uncalibrated.** Using a model to score outputs without checking judge agreement with humans. Produces confident nonsense.
- **Benchmark-fit, not product-fit.** Optimizing against public benchmarks that correlate weakly with your product's actual value.
- **Over-engineering agents.** Building a multi-step agent for a task that works fine as a single prompt. Debt accumulates fast.
- **Ignoring retrieval quality.** Spending weeks on prompt tweaks when the retrieval step has 40% recall.
- **Prompt sprawl.** Dozens of prompts embedded in code, no versioning, no eval linkage. Every change is a silent risk.
- **Cost surprise.** Users adopt faster than projected; a feature that was fine at 1k calls/day is catastrophic at 100k. Cost-per-outcome projections must include upper bounds.
- **Silent model-version upgrades.** Provider updates model behavior without notice; evals regress. Subscribe to changelogs, pin versions where supported.
- **Not shipping evals with the feature.** Evals live in a notebook; the feature ships; evals are never run again. The eval harness must be CI-grade or it decays.
- **Human-override mistaken for edge case.** Overrides are often the first visible signal of a systematic weakness, not a random outlier.

---

## Practical principles

- **Every AI behavior claim requires an eval.** "It's better at X" is not a statement that survives the next prompt tweak without an eval to back it up.
- **Ship the eval harness before the feature.** Otherwise you cannot tell whether changes help or regress.
- **Cost and latency are product properties, not infra concerns.** Users feel both; PMs own both.
- **Re-run evals on every model version change.** Silent upgrades from providers have broken many pipelines.
- **Abstract over models where feasible.** Model-agnostic interfaces let you switch providers when one degrades.
- **Human override is a metric to track, not a feature to hide.** It is signal about where the model is currently weak.
- **Small, focused evals beat big benchmarks.** A public benchmark correlates weakly with your product's value. Build your own.
- **Don't over-engineer agents before single-turn tasks are reliable.** Multi-step failures compound.
- **Look at your data.** Husain's emphasis: read actual production outputs weekly. Dashboards lie; raw outputs don't.
- **Publish what you know.** Model cards, system prompts, known limits, refusal rules. Users trust transparency more than marketing.
