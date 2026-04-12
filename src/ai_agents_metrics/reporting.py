from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.domain import (
    EffectiveGoalRecord,
    build_effective_goals,
    goal_from_dict,
)
from ai_agents_metrics.redaction import redact_text

if TYPE_CHECKING:
    from ai_agents_metrics.history_compare import HistorySignals


@dataclass(frozen=True)
class ProductQualitySummary:
    closed_product_goals: int
    successful_product_goals: int
    failed_product_goals: int
    reviewed_product_goals: int
    unreviewed_product_goals: int
    exact_fit_goals: int
    partial_fit_goals: int
    miss_goals: int
    exact_fit_rate_reviewed: float | None
    miss_rate_reviewed: float | None
    review_coverage: float | None
    attempts_per_closed_product_goal: float | None
    known_cost_successes: int
    known_token_successes: int
    known_cost_per_success_usd: float | None
    known_cost_per_success_tokens: float | None


@dataclass(frozen=True)
class AgentRecommendation:
    category: str
    priority: str
    diagnosis: str
    next_action: str


def _effective_goals_from_data(data: dict[str, Any]) -> list[EffectiveGoalRecord]:
    return build_effective_goals([goal_from_dict(goal) for goal in data["goals"]])


def build_product_quality_summary(data: dict[str, Any]) -> ProductQualitySummary:
    effective_goals = _effective_goals_from_data(data)
    closed_product_goals = [
        goal for goal in effective_goals if goal.goal_type == "product" and goal.status in {"success", "fail"}
    ]
    reviewed_product_goals = [goal for goal in closed_product_goals if goal.result_fit is not None]
    exact_fit_goals = [goal for goal in reviewed_product_goals if goal.result_fit == "exact_fit"]
    partial_fit_goals = [goal for goal in reviewed_product_goals if goal.result_fit == "partial_fit"]
    miss_goals = [goal for goal in reviewed_product_goals if goal.result_fit == "miss"]
    successful_product_goals = [goal for goal in closed_product_goals if goal.status == "success"]
    failed_product_goals = [goal for goal in closed_product_goals if goal.status == "fail"]
    known_cost_successes = [goal for goal in successful_product_goals if goal.cost_usd_known is not None]
    known_token_successes = [goal for goal in successful_product_goals if goal.tokens_total_known is not None]
    known_success_cost_total = sum(goal.cost_usd_known or 0.0 for goal in known_cost_successes)
    known_success_token_total = sum(goal.tokens_total_known or 0 for goal in known_token_successes)
    total_closed = len(closed_product_goals)
    reviewed_count = len(reviewed_product_goals)

    return ProductQualitySummary(
        closed_product_goals=total_closed,
        successful_product_goals=len(successful_product_goals),
        failed_product_goals=len(failed_product_goals),
        reviewed_product_goals=reviewed_count,
        unreviewed_product_goals=total_closed - reviewed_count,
        exact_fit_goals=len(exact_fit_goals),
        partial_fit_goals=len(partial_fit_goals),
        miss_goals=len(miss_goals),
        exact_fit_rate_reviewed=(len(exact_fit_goals) / reviewed_count) if reviewed_count else None,
        miss_rate_reviewed=(len(miss_goals) / reviewed_count) if reviewed_count else None,
        review_coverage=(reviewed_count / total_closed) if total_closed else None,
        attempts_per_closed_product_goal=(
            sum(goal.attempts for goal in closed_product_goals) / total_closed if total_closed else None
        ),
        known_cost_successes=len(known_cost_successes),
        known_token_successes=len(known_token_successes),
        known_cost_per_success_usd=(
            known_success_cost_total / len(known_cost_successes) if known_cost_successes else None
        ),
        known_cost_per_success_tokens=(
            known_success_token_total / len(known_token_successes) if known_token_successes else None
        ),
    )


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def format_num(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def format_usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    formatted = f"{value:.6f}".rstrip("0").rstrip(".")
    if "." not in formatted:
        return f"{formatted}.00"
    fractional_part = formatted.split(".", maxsplit=1)[1]
    if len(fractional_part) < 2:
        return formatted + ("0" * (2 - len(fractional_part)))
    return formatted


def format_coverage(known_count: int, total_count: int) -> str:
    if total_count == 0:
        return "n/a"
    return f"{known_count}/{total_count}"


def format_token_breakdown(input_tokens: int | None, cached_input_tokens: int | None, output_tokens: int | None) -> str:
    if input_tokens is None and cached_input_tokens is None and output_tokens is None:
        return "n/a"
    return (
        f"input={format_num(input_tokens)}, "
        f"cached={format_num(cached_input_tokens)}, "
        f"output={format_num(output_tokens)}"
    )


def build_agent_recommendations(summary: dict[str, Any], product_quality: ProductQualitySummary) -> list[AgentRecommendation]:
    recommendations: list[AgentRecommendation] = []
    product_summary = summary["by_goal_type"]["product"]
    entry_summary = summary["entries"]
    successes = summary["successes"]

    if product_quality.closed_product_goals == 0:
        recommendations.append(
            AgentRecommendation(
                category="product_sample",
                priority="high",
                diagnosis="No closed product goals exist yet, so quality conclusions are not ready.",
                next_action="Use ai-agents-metrics on real product goals before drawing workflow conclusions.",
            )
        )
        return recommendations

    if product_quality.reviewed_product_goals == 0:
        recommendations.append(
            AgentRecommendation(
                category="quality_review_coverage",
                priority="high",
                diagnosis="Product quality review has not started, so result-fit signals are still missing.",
                next_action="Backfill result_fit for recent closed product goals before trusting quality trends.",
            )
        )
    elif product_quality.unreviewed_product_goals > 0:
        recommendations.append(
            AgentRecommendation(
                category="quality_review_coverage",
                priority="medium",
                diagnosis="Product quality review coverage is partial, so fit rates only reflect a reviewed subset.",
                next_action="Review unreviewed product goals to raise result-fit coverage before making strong workflow decisions.",
            )
        )

    if product_quality.miss_goals > 0:
        recommendations.append(
            AgentRecommendation(
                category="quality_miss",
                priority="high",
                diagnosis="Reviewed product misses exist, which means at least some requested outcomes still failed outright.",
                next_action="Inspect missed product goals first and identify whether the dominant issue was scope clarity, context, or execution.",
            )
        )

    if product_quality.partial_fit_goals > 0:
        recommendations.append(
            AgentRecommendation(
                category="quality_partial_fit",
                priority="medium",
                diagnosis="Reviewed partial-fit outcomes exist, so some product goals only succeeded after correction.",
                next_action="Inspect the partial-fit product goals and look for acceptance drift or avoidable follow-up work.",
            )
        )

    if product_quality.attempts_per_closed_product_goal is not None and product_quality.attempts_per_closed_product_goal > 1.2:
        recommendations.append(
            AgentRecommendation(
                category="retry_pressure",
                priority="medium",
                diagnosis="Product retry pressure looks elevated relative to a simple one-pass flow.",
                next_action="Inspect recent retries and continuation chains to see whether requirements or task boundaries need tightening.",
            )
        )

    if product_summary["closed_tasks"] < 5:
        recommendations.append(
            AgentRecommendation(
                category="product_sample",
                priority="medium",
                diagnosis="The closed product-goal sample is still small, so workflow conclusions remain provisional.",
                next_action="Collect more real product-goal history before generalizing from the current trend.",
            )
        )

    if summary["by_goal_type"]["meta"]["closed_tasks"] > product_summary["closed_tasks"]:
        recommendations.append(
            AgentRecommendation(
                category="product_mix",
                priority="medium",
                diagnosis="Meta work still outweighs product delivery, so local optimizations may not transfer cleanly to real product work.",
                next_action="Validate any workflow changes on real product goals before treating them as product-level improvements.",
            )
        )

    if entry_summary["fails"] > 0:
        top_reason = None
        if entry_summary["failure_reasons"]:
            top_reason = max(entry_summary["failure_reasons"].items(), key=lambda item: item[1])[0]
        recommendations.append(
            AgentRecommendation(
                category="entry_failures",
                priority="medium",
                diagnosis=(
                    "Failed entries exist, which means retry pressure is still present in the underlying attempt history."
                    if top_reason is None
                    else f"Failed entries exist, especially around {top_reason}."
                ),
                next_action=(
                    "Inspect failed entries and recent attempt chains before concluding that the workflow is stable."
                    if top_reason is None
                    else f"Inspect failed entries tagged {top_reason} and the linked goals before recommending further process changes."
                ),
            )
        )

    if product_quality.successful_product_goals > 0 and product_quality.known_cost_successes < product_quality.successful_product_goals:
        recommendations.append(
            AgentRecommendation(
                category="product_cost_coverage",
                priority="low",
                diagnosis="Known product cost coverage is still partial, so product cost averages remain directional rather than complete.",
                next_action="Use product cost views as guidance only and backfill or sync missing usage when cost comparisons matter for a decision.",
            )
        )

    if successes > 0 and summary["complete_cost_successes"] < successes and summary["known_cost_per_success_usd"] is not None:
        recommendations.append(
            AgentRecommendation(
                category="global_cost_coverage",
                priority="low",
                diagnosis="Complete cost coverage is still partial across the full history, so complete covered-success averages are a strict subset view.",
                next_action="Avoid over-reading complete-cost averages as if they described the whole dataset.",
            )
        )

    if not recommendations:
        recommendations.append(
            AgentRecommendation(
                category="stability",
                priority="low",
                diagnosis="Current signals look stable enough for another cycle of workflow comparison.",
                next_action="Keep collecting product-goal history and compare the next workflow change against this baseline.",
            )
        )

    return recommendations


def build_operator_review(summary: dict[str, Any]) -> list[str]:
    product_summary = summary["by_goal_type"]["product"]
    product_quality = ProductQualitySummary(
        closed_product_goals=product_summary["closed_tasks"],
        successful_product_goals=product_summary.get("successes", 0),
        failed_product_goals=product_summary.get("fails", 0),
        reviewed_product_goals=0,
        unreviewed_product_goals=product_summary["closed_tasks"],
        exact_fit_goals=0,
        partial_fit_goals=0,
        miss_goals=0,
        exact_fit_rate_reviewed=None,
        miss_rate_reviewed=None,
        review_coverage=0.0 if product_summary["closed_tasks"] else None,
        attempts_per_closed_product_goal=product_summary.get("attempts_per_closed_task"),
        known_cost_successes=product_summary.get("known_cost_successes", 0),
        known_token_successes=product_summary.get("known_token_successes", 0),
        known_cost_per_success_usd=product_summary.get("known_cost_per_success_usd"),
        known_cost_per_success_tokens=product_summary.get("known_cost_per_success_tokens"),
    )
    return [recommendation.diagnosis for recommendation in build_agent_recommendations(summary, product_quality)]


def build_quality_review(summary: ProductQualitySummary) -> list[str]:
    filtered = [
        recommendation.diagnosis
        for recommendation in build_agent_recommendations(
            {
                "successes": 0,
                "known_cost_successes": 0,
                "known_cost_per_success_usd": None,
                "complete_cost_successes": 0,
                "complete_cost_per_covered_success_usd": None,
                "by_goal_type": {
                    "product": {"closed_tasks": summary.closed_product_goals},
                    "retro": {"closed_tasks": 0},
                    "meta": {"closed_tasks": 0},
                },
                "entries": {"fails": 0, "failure_reasons": {}},
            },
            summary,
        )
        if recommendation.category in {"product_sample", "quality_review_coverage", "quality_miss", "quality_partial_fit", "retry_pressure"}
    ]
    return filtered


def _format_recommendation(recommendation: AgentRecommendation) -> str:
    return (
        f"[{recommendation.priority}] {recommendation.category}: "
        f"{recommendation.diagnosis} Next action: {recommendation.next_action}"
    )


def _product_quality_lines(product_quality: ProductQualitySummary) -> list[str]:
    return [
        "## Product quality",
        "",
        f"- Closed product goals: {product_quality.closed_product_goals}",
        (
            f"- Reviewed result fit: {product_quality.reviewed_product_goals}/"
            f"{product_quality.closed_product_goals} closed product goals"
        ),
        f"- Review coverage: {format_pct(product_quality.review_coverage)}",
        f"- Exact fit: {product_quality.exact_fit_goals}",
        f"- Partial fit: {product_quality.partial_fit_goals}",
        f"- Misses: {product_quality.miss_goals}",
        f"- Unreviewed: {product_quality.unreviewed_product_goals}",
        f"- Exact Fit Rate (reviewed): {format_pct(product_quality.exact_fit_rate_reviewed)}",
        f"- Miss Rate (reviewed): {format_pct(product_quality.miss_rate_reviewed)}",
        f"- Attempts per Closed Product Goal: {format_num(product_quality.attempts_per_closed_product_goal)}",
        (
            f"- Known product cost coverage: "
            f"{format_coverage(product_quality.known_cost_successes, product_quality.successful_product_goals)} "
            "successful product goals"
        ),
        f"- Known Product Cost per Success (USD): {format_usd(product_quality.known_cost_per_success_usd)}",
        f"- Known Product Cost per Success (Tokens): {format_num(product_quality.known_cost_per_success_tokens)}",
        "",
        "## Agent recommendations",
        "",
    ]


def _model_summary_lines(model: str, model_summary: dict[str, Any]) -> list[str]:
    return [
        f"### {model}",
        f"- Closed goals: {model_summary['closed_tasks']}",
        f"- Successes: {model_summary['successes']}",
        f"- Fails: {model_summary['fails']}",
        f"- Total attempts: {model_summary['total_attempts']}",
        f"- Known total cost (USD): {format_usd(model_summary['total_cost_usd'])}",
        (
            "- Known token breakdown totals: "
            f"{format_token_breakdown(model_summary.get('total_input_tokens'), model_summary.get('total_cached_input_tokens'), model_summary.get('total_output_tokens'))}"
        ),
        f"- Known total tokens: {model_summary['total_tokens']}",
        f"- Success Rate: {format_pct(model_summary['success_rate'])}",
        f"- Attempts per Closed Goal: {format_num(model_summary['attempts_per_closed_task'])}",
        f"- Known cost coverage: {format_coverage(model_summary['known_cost_successes'], model_summary['successes'])} successful goals",
        f"- Known token coverage: {format_coverage(model_summary['known_token_successes'], model_summary['successes'])} successful goals",
        f"- Known token breakdown coverage: {format_coverage(model_summary.get('known_token_breakdown_successes', 0), model_summary['successes'])} successful goals",
        f"- Complete cost coverage: {format_coverage(model_summary['complete_cost_successes'], model_summary['successes'])} successful goals",
        f"- Complete token coverage: {format_coverage(model_summary['complete_token_successes'], model_summary['successes'])} successful goals",
        f"- Complete token breakdown coverage: {format_coverage(model_summary.get('complete_token_breakdown_successes', 0), model_summary['successes'])} successful goals",
        f"- Known Cost per Success (USD): {format_usd(model_summary['known_cost_per_success_usd'])}",
        f"- Known Cost per Success (Tokens): {format_num(model_summary['known_cost_per_success_tokens'])}",
        f"- Complete Cost per Covered Success (USD): {format_usd(model_summary['complete_cost_per_covered_success_usd'])}",
        f"- Complete Cost per Covered Success (Tokens): {format_num(model_summary['complete_cost_per_covered_success_tokens'])}",
        "",
    ]


def generate_report_md(data: dict[str, Any]) -> str:
    summary = data["summary"]
    goals: list[dict[str, Any]] = data["goals"]
    entries: list[dict[str, Any]] = data["entries"]
    product_quality = build_product_quality_summary(data)
    recommendations = build_agent_recommendations(summary, product_quality)

    lines: list[str] = [
        "# Codex Metrics",
        "",
    ]
    lines.extend(_product_quality_lines(product_quality))
    lines.extend(f"- {_format_recommendation(recommendation)}" for recommendation in recommendations)
    lines.extend(
        [
            "",
            "## Operational summary",
            "",
            f"- Closed goals: {summary['closed_tasks']}",
            f"- Successes: {summary['successes']}",
            f"- Fails: {summary['fails']}",
            f"- Total attempts: {summary['total_attempts']}",
            f"- Known total cost (USD): {format_usd(summary['total_cost_usd'])}",
            (
                "- Known token breakdown totals: "
                f"{format_token_breakdown(summary.get('total_input_tokens'), summary.get('total_cached_input_tokens'), summary.get('total_output_tokens'))}"
            ),
            f"- Known total tokens: {summary['total_tokens']}",
            f"- Success Rate: {format_pct(summary['success_rate'])}",
            f"- Attempts per Closed Goal: {format_num(summary['attempts_per_closed_task'])}",
            f"- Model coverage: {format_coverage(summary.get('model_summary_goals', 0), summary['closed_tasks'])} closed goals with an unambiguous model",
            f"- Model-complete goals: {summary.get('model_complete_goals', 0)}",
            f"- Mixed-model goals: {summary.get('mixed_model_goals', 0)}",
            f"- Known cost coverage: {format_coverage(summary['known_cost_successes'], summary['successes'])} successful goals",
            f"- Known token coverage: {format_coverage(summary['known_token_successes'], summary['successes'])} successful goals",
            f"- Known token breakdown coverage: {format_coverage(summary.get('known_token_breakdown_successes', 0), summary['successes'])} successful goals",
            f"- Complete cost coverage: {format_coverage(summary['complete_cost_successes'], summary['successes'])} successful goals",
            f"- Complete token coverage: {format_coverage(summary['complete_token_successes'], summary['successes'])} successful goals",
            f"- Complete token breakdown coverage: {format_coverage(summary.get('complete_token_breakdown_successes', 0), summary['successes'])} successful goals",
            f"- Known Cost per Success (USD): {format_usd(summary['known_cost_per_success_usd'])}",
            f"- Known Cost per Success (Tokens): {format_num(summary['known_cost_per_success_tokens'])}",
            f"- Complete Cost per Covered Success (USD): {format_usd(summary['complete_cost_per_covered_success_usd'])}",
            f"- Complete Cost per Covered Success (Tokens): {format_num(summary['complete_cost_per_covered_success_tokens'])}",
            "",
            "## By model",
            "",
        ]
    )
    if summary.get("by_model"):
        for model, model_summary in sorted(summary["by_model"].items()):
            lines.extend(_model_summary_lines(model, model_summary))
    else:
        lines.extend(["_No unambiguous model summaries available yet._", ""])
    lines.extend(
        [
            "## Entry summary",
            "",
            f"- Closed entries: {summary['entries']['closed_entries']}",
            f"- Successes: {summary['entries']['successes']}",
            f"- Fails: {summary['entries']['fails']}",
            f"- Success Rate: {format_pct(summary['entries']['success_rate'])}",
            f"- Known total cost (USD): {format_usd(summary['entries']['total_cost_usd'])}",
            (
                "- Known token breakdown totals: "
                f"{format_token_breakdown(summary['entries'].get('total_input_tokens'), summary['entries'].get('total_cached_input_tokens'), summary['entries'].get('total_output_tokens'))}"
            ),
            f"- Known total tokens: {summary['entries']['total_tokens']}",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "## By goal type",
            "",
        ]
    )

    failure_reasons = summary["entries"]["failure_reasons"]
    if failure_reasons:
        lines.extend(
            [
                "### Entry failure reasons",
            ]
        )
        for reason, count in failure_reasons.items():
            lines.append(f"- {reason}: {count}")
        lines.append("")

    for task_type in ("product", "retro", "meta"):
        type_summary = summary["by_goal_type"][task_type]
        lines.extend(
            [
                f"### {task_type}",
                f"- Closed goals: {type_summary['closed_tasks']}",
                f"- Successes: {type_summary['successes']}",
                f"- Fails: {type_summary['fails']}",
                f"- Total attempts: {type_summary['total_attempts']}",
                f"- Known total cost (USD): {format_usd(type_summary['total_cost_usd'])}",
                (
                    "- Known token breakdown totals: "
                    f"{format_token_breakdown(type_summary.get('total_input_tokens'), type_summary.get('total_cached_input_tokens'), type_summary.get('total_output_tokens'))}"
                ),
                f"- Known total tokens: {type_summary['total_tokens']}",
                f"- Success Rate: {format_pct(type_summary['success_rate'])}",
                f"- Attempts per Closed Goal: {format_num(type_summary['attempts_per_closed_task'])}",
                f"- Known cost coverage: {format_coverage(type_summary['known_cost_successes'], type_summary['successes'])} successful goals",
                f"- Known token coverage: {format_coverage(type_summary['known_token_successes'], type_summary['successes'])} successful goals",
                f"- Known token breakdown coverage: {format_coverage(type_summary.get('known_token_breakdown_successes', 0), type_summary['successes'])} successful goals",
                f"- Complete cost coverage: {format_coverage(type_summary['complete_cost_successes'], type_summary['successes'])} successful goals",
                f"- Complete token coverage: {format_coverage(type_summary['complete_token_successes'], type_summary['successes'])} successful goals",
                f"- Complete token breakdown coverage: {format_coverage(type_summary.get('complete_token_breakdown_successes', 0), type_summary['successes'])} successful goals",
                f"- Known Cost per Success (USD): {format_usd(type_summary['known_cost_per_success_usd'])}",
                f"- Known Cost per Success (Tokens): {format_num(type_summary['known_cost_per_success_tokens'])}",
                f"- Complete Cost per Covered Success (USD): {format_usd(type_summary['complete_cost_per_covered_success_usd'])}",
                f"- Complete Cost per Covered Success (Tokens): {format_num(type_summary['complete_cost_per_covered_success_tokens'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## Goal log",
            "",
        ]
    )

    if not goals:
        lines.append("_No goals recorded yet._")
        lines.append("")
        return "\n".join(lines)

    for task in sorted(goals, key=lambda x: x.get("started_at") or "", reverse=True):
        title = redact_text(str(task["title"]))
        notes = redact_text(str(task.get("notes") or "n/a"))
        lines.extend(
            [
                f"### {task['goal_id']} — {title}",
                f"- Goal type: {task['goal_type']}",
                f"- Supersedes goal: {task.get('supersedes_goal_id') or 'n/a'}",
                f"- Status: {task['status']}",
                f"- Agent: {task.get('agent_name') or 'n/a'}",
                f"- Model: {task.get('model') or 'n/a'}",
                f"- Attempts: {task['attempts']}",
                f"- Started at: {task['started_at'] or 'n/a'}",
                f"- Finished at: {task['finished_at'] or 'n/a'}",
                f"- Cost (USD): {format_usd(task.get('cost_usd'))}",
                (
                    "- Token breakdown: "
                    f"{format_token_breakdown(task.get('input_tokens'), task.get('cached_input_tokens'), task.get('output_tokens'))}"
                ),
                f"- Tokens: {format_num(task.get('tokens_total'))}",
                f"- Failure reason: {task.get('failure_reason') or 'n/a'}",
                f"- Result fit: {task.get('result_fit') or 'n/a'}",
                f"- Notes: {notes}",
                "",
            ]
        )

    lines.extend(
        [
            "## Entry log",
            "",
        ]
    )
    for entry in sorted(entries, key=lambda x: x.get("started_at") or "", reverse=True):
        lines.extend(
            [
                f"### {entry['entry_id']} — {entry['goal_id']}",
                f"- Entry type: {entry['entry_type']}",
                f"- Inferred: {'yes' if entry.get('inferred') else 'no'}",
                f"- Status: {entry['status']}",
                f"- Agent: {entry.get('agent_name') or 'n/a'}",
                f"- Model: {entry.get('model') or 'n/a'}",
                f"- Started at: {entry['started_at'] or 'n/a'}",
                f"- Finished at: {entry['finished_at'] or 'n/a'}",
                f"- Cost (USD): {format_usd(entry.get('cost_usd'))}",
                (
                    "- Token breakdown: "
                    f"{format_token_breakdown(entry.get('input_tokens'), entry.get('cached_input_tokens'), entry.get('output_tokens'))}"
                ),
                f"- Tokens: {format_num(entry.get('tokens_total'))}",
                f"- Failure reason: {entry.get('failure_reason') or 'n/a'}",
                f"- Notes: {entry.get('notes') or 'n/a'}",
                "",
            ]
        )

    return "\n".join(lines)


def print_summary(data: dict[str, Any], history_signals: HistorySignals | None = None) -> None:
    summary = data["summary"]
    product_quality = build_product_quality_summary(data)
    recommendations = build_agent_recommendations(summary, product_quality)
    print("Codex Metrics Summary")
    print("Product quality:")
    print(f"Closed product goals: {product_quality.closed_product_goals}")
    print(
        f"Reviewed result fit: {product_quality.reviewed_product_goals}/"
        f"{product_quality.closed_product_goals} closed product goals"
    )
    print(f"Review coverage: {format_pct(product_quality.review_coverage)}")
    print(f"Exact fit: {product_quality.exact_fit_goals}")
    print(f"Partial fit: {product_quality.partial_fit_goals}")
    print(f"Misses: {product_quality.miss_goals}")
    print(f"Unreviewed: {product_quality.unreviewed_product_goals}")
    print(f"Exact Fit Rate (reviewed): {format_pct(product_quality.exact_fit_rate_reviewed)}")
    print(f"Miss Rate (reviewed): {format_pct(product_quality.miss_rate_reviewed)}")
    print(f"Attempts per Closed Product Goal: {format_num(product_quality.attempts_per_closed_product_goal)}")
    print(
        f"Known product cost coverage: "
        f"{format_coverage(product_quality.known_cost_successes, product_quality.successful_product_goals)} "
        "successful product goals"
    )
    print(f"Known Product Cost per Success (USD): {format_usd(product_quality.known_cost_per_success_usd)}")
    print(f"Known Product Cost per Success (Tokens): {format_num(product_quality.known_cost_per_success_tokens)}")
    print("Agent recommendations:")
    for recommendation in recommendations:
        print(f"- {_format_recommendation(recommendation)}")
    print("Operational summary:")
    print(f"Closed goals: {summary['closed_tasks']}")
    print(f"Successes: {summary['successes']}")
    print(f"Fails: {summary['fails']}")
    print(f"Total attempts: {summary['total_attempts']}")
    print(f"Known total cost (USD): {format_usd(summary['total_cost_usd'])}")
    print(
        "Known token breakdown totals: "
        f"{format_token_breakdown(summary.get('total_input_tokens'), summary.get('total_cached_input_tokens'), summary.get('total_output_tokens'))}"
    )
    print(f"Known total tokens: {summary['total_tokens']}")
    print(f"Success Rate: {format_pct(summary['success_rate'])}")
    print(f"Attempts per Closed Goal: {format_num(summary['attempts_per_closed_task'])}")
    print(
        f"Model coverage: {format_coverage(summary.get('model_summary_goals', 0), summary['closed_tasks'])} "
        "closed goals with an unambiguous model"
    )
    print(f"Model-complete goals: {summary.get('model_complete_goals', 0)}")
    print(f"Mixed-model goals: {summary.get('mixed_model_goals', 0)}")
    print(f"Known cost coverage: {format_coverage(summary['known_cost_successes'], summary['successes'])} successful goals")
    print(f"Known token coverage: {format_coverage(summary['known_token_successes'], summary['successes'])} successful goals")
    print(
        f"Known token breakdown coverage: "
        f"{format_coverage(summary.get('known_token_breakdown_successes', 0), summary['successes'])} successful goals"
    )
    print(f"Complete cost coverage: {format_coverage(summary['complete_cost_successes'], summary['successes'])} successful goals")
    print(f"Complete token coverage: {format_coverage(summary['complete_token_successes'], summary['successes'])} successful goals")
    print(
        f"Complete token breakdown coverage: "
        f"{format_coverage(summary.get('complete_token_breakdown_successes', 0), summary['successes'])} successful goals"
    )
    print(f"Known Cost per Success (USD): {format_usd(summary['known_cost_per_success_usd'])}")
    print(f"Known Cost per Success (Tokens): {format_num(summary['known_cost_per_success_tokens'])}")
    print(f"Complete Cost per Covered Success (USD): {format_usd(summary['complete_cost_per_covered_success_usd'])}")
    print(f"Complete Cost per Covered Success (Tokens): {format_num(summary['complete_cost_per_covered_success_tokens'])}")
    print("By model:")
    if summary.get("by_model"):
        for model, model_summary in sorted(summary["by_model"].items()):
            print(f"- {model}: {model_summary['closed_tasks']} closed, {model_summary['successes']} successes, {model_summary['fails']} fails")
    else:
        print("- n/a")
    print(f"Closed entries: {summary['entries']['closed_entries']}")
    print(f"Entry successes: {summary['entries']['successes']}")
    print(f"Entry fails: {summary['entries']['fails']}")
    print(f"Entry Success Rate: {format_pct(summary['entries']['success_rate'])}")
    print(
        "Entry token breakdown totals: "
        f"{format_token_breakdown(summary['entries'].get('total_input_tokens'), summary['entries'].get('total_cached_input_tokens'), summary['entries'].get('total_output_tokens'))}"
    )
    for task_type in ("product", "retro", "meta"):
        type_summary = summary["by_goal_type"][task_type]
        print(
            f"{task_type.title()} goals: {type_summary['closed_tasks']} closed, "
            f"{type_summary['successes']} successes, {type_summary['fails']} fails"
        )
    if summary["entries"]["failure_reasons"]:
        print("Entry failure reasons:")
        for reason, count in summary["entries"]["failure_reasons"].items():
            print(f"- {reason}: {count}")
    if history_signals is not None:
        scope_label = "all projects" if history_signals.is_all_projects else "warehouse"
        print(f"History signals ({scope_label}):")
        if history_signals.is_all_projects:
            print("  (no history for current directory — showing all projects)")
        retry_pct = f"{history_signals.retry_rate:.0%}"
        print(f"  Project threads: {history_signals.project_threads}  (worktrees merged)")
        print(f"  Threads with retry pressure: {history_signals.retry_threads} / {history_signals.project_threads} ({retry_pct})")
        print(f"  Per-goal alignment: {history_signals.ledger_goal_alignments} / {history_signals.ledger_goals_total} ledger goals matched to history window")


def render_summary_json(data: dict[str, Any], history_signals: HistorySignals | None = None) -> str:
    product_quality = build_product_quality_summary(data)
    recommendations = build_agent_recommendations(data["summary"], product_quality)
    return json.dumps({
        "product_quality": {
            "closed_product_goals": product_quality.closed_product_goals,
            "successful_product_goals": product_quality.successful_product_goals,
            "failed_product_goals": product_quality.failed_product_goals,
            "reviewed_product_goals": product_quality.reviewed_product_goals,
            "unreviewed_product_goals": product_quality.unreviewed_product_goals,
            "exact_fit_goals": product_quality.exact_fit_goals,
            "partial_fit_goals": product_quality.partial_fit_goals,
            "miss_goals": product_quality.miss_goals,
            "exact_fit_rate_reviewed": product_quality.exact_fit_rate_reviewed,
            "miss_rate_reviewed": product_quality.miss_rate_reviewed,
            "review_coverage": product_quality.review_coverage,
            "attempts_per_closed_product_goal": product_quality.attempts_per_closed_product_goal,
            "known_cost_successes": product_quality.known_cost_successes,
            "known_token_successes": product_quality.known_token_successes,
            "known_cost_per_success_usd": product_quality.known_cost_per_success_usd,
            "known_cost_per_success_tokens": product_quality.known_cost_per_success_tokens,
        },
        "recommendations": [
            {
                "category": r.category,
                "priority": r.priority,
                "diagnosis": r.diagnosis,
                "next_action": r.next_action,
            }
            for r in recommendations
        ],
        "summary": data["summary"],
        "goals": data["goals"],
        "entries": data["entries"],
        "history_signals": {
            "scope": "all_projects" if history_signals.is_all_projects else "current_project",
            "project_threads": history_signals.project_threads,
            "retry_threads": history_signals.retry_threads,
            "retry_rate": history_signals.retry_rate,
            "ledger_goal_alignments": history_signals.ledger_goal_alignments,
            "ledger_goals_total": history_signals.ledger_goals_total,
        } if history_signals is not None else None,
    })
