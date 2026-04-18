# Systems Thinking

The meta-layer: seeing the system, finding the real bottleneck, intervening at the highest-leverage point.

## Canonical sources

- **Donella Meadows** — *Thinking in Systems: A Primer*. The single best introduction to systems thinking. Introduces stocks, flows, feedback loops, delays, and the famous "Leverage Points" essay (12 places to intervene in a system, ranked).
- **Eliyahu Goldratt** — *The Goal*, *Theory of Constraints*. Business novel form. The Five Focusing Steps: identify the constraint, exploit it, subordinate everything else to it, elevate it, repeat.
- **W. Edwards Deming** — *Out of the Crisis*, *The New Economics*. The 14 Points; the System of Profound Knowledge (appreciation for systems, theory of variation, theory of knowledge, psychology). Quality as a system property.
- **Taiichi Ohno** — *Toyota Production System*. The originator of lean manufacturing. Pull systems, waste elimination (muda), Five Whys, Andon cords.
- **Christopher Alexander** — *A Pattern Language*, *The Timeless Way of Building*. Architectural theory that became foundational to software design patterns.
- **Nassim Taleb** — *Antifragile*, *Skin in the Game*, *The Black Swan*. Asymmetry, convex vs concave exposures, via negativa, optionality.
- **Peter Senge** — *The Fifth Discipline*. Systems thinking applied to organizational learning. The archetypes (limits to growth, shifting the burden, tragedy of the commons, etc.).

## Core concepts

- **Stocks and flows.** Stocks are accumulations (users, cash, trust, tech debt); flows are rates of change (signups, revenue, burn). Most metrics are stocks; most interventions change flows. Confusing the two is the default PM mistake.
- **Feedback loops.** *Reinforcing* loops amplify change (growth loops, viral spread, death spirals). *Balancing* loops stabilize around a setpoint (regulation, satiation). Systems behavior emerges from the dominant loop.
- **Delays.** Feedback with delay produces oscillation. Many "mysterious" product problems are delayed feedback.
- **Leverage points (Meadows, 12 levels).** From weakest to strongest: constants/parameters → buffer sizes → stock-flow structures → delays → balancing loops → reinforcing loops → information flows → rules → self-organization → goals → paradigm → transcending paradigms. Most interventions target the weakest levels.
- **Theory of Constraints (Goldratt).** A system's throughput is limited by exactly one constraint at a time. Optimizing anything else is at best waste, at worst harmful (local optima).
- **Five Focusing Steps.** Identify → exploit → subordinate → elevate → repeat. The discipline of not optimizing non-constraints.
- **Five Whys.** Keep asking why until you reach a cause, not a symptom. Practitioners often stop one or two whys too early.
- **Archetypes (Senge).** Recurring patterns: limits to growth, shifting the burden, tragedy of the commons, escalation, success to the successful, fixes that fail.
- **Antifragility (Taleb).** Fragile systems break from shocks; robust systems absorb them; antifragile systems benefit from them. Design for antifragility via optionality and convex exposure.

## Practical principles

- **Before optimizing anything, identify the constraint.** Goldratt's rule. Optimizing a non-constraint yields no throughput gain — sometimes a loss.
- **Fix the system, not the incident.** The bug is the symptom; the defect that allowed the bug in is the target.
- **The Five Whys are rarely done to completion.** Most teams stop at the first "why" that feels actionable, which is almost always a symptom.
- **Work the upstream feedback, not the downstream metric.** If you find yourself chasing a number that won't budge, step upstream until you find the flow that feeds the stock.
- **Prefer safe-to-fail experiments over fail-safe designs** when the system's behavior is uncertain. You cannot engineer away uncertainty; you can make failures cheap and observable.
- **Beware of success.** Reinforcing loops eventually hit limits. The question is not "will growth stall?" but "which limit will stall it first?"
- **Variation is a property of the system, not the operator.** Deming's rule. Blaming individuals for common-cause variation makes things worse.
