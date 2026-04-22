"""CLI handlers for history ingestion, normalization, derivation, and related audits."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ai_agents_metrics.cost_audit import render_cost_audit_report

if TYPE_CHECKING:
    from argparse import Namespace

    from ai_agents_metrics.commands._runtime import CommandRuntime
    from ai_agents_metrics.history.ingest import IngestSummary


def _run_ingest(
    source: str,
    source_root_arg: str | None,
    warehouse_path: Path,
    cli_module: CommandRuntime,
) -> tuple[dict[str, IngestSummary], list[str], str | None]:
    """Run ingest for the resolved source(s).

    Returns (summaries_by_source, skipped_source_names, error_message).
    error_message is non-None for invalid argument combinations.
    """
    if source == "all":
        if source_root_arg is not None:
            return {}, [], "--source-root cannot be used with --source all"
        summaries: dict[str, IngestSummary] = {}
        skipped: list[str] = []
        for src_name, src_root in [("codex", Path.home() / ".codex"), ("claude", Path.home() / ".claude")]:
            if not src_root.exists():
                skipped.append(src_name)
                continue
            with cli_module.metrics_mutation_lock(warehouse_path):
                summaries[src_name] = cli_module.ingest_codex_history(src_root, warehouse_path, src_name)
        return summaries, skipped, None

    if source_root_arg is not None:
        source_root = Path(source_root_arg).expanduser()
    elif source == "claude":
        source_root = Path.home() / ".claude"
    else:
        source_root = Path.home() / ".codex"
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.ingest_codex_history(source_root, warehouse_path, source)
    return {source: summary}, [], None


def _print_empty_history_guidance(source: str) -> None:
    """Print actionable next steps when no agent history is found on first run.

    Called from ``handle_history_update`` when the default-location scan
    finds no Codex or Claude Code history files. The tool's core value
    proposition is extracting signals from these history files — a fresh
    user seeing a terse "nothing to normalize" line does not know whether
    the tool is broken, whether their history is in the wrong place, or
    whether they need to generate some agent activity first.
    """
    claude_dir = Path.home() / ".claude"
    codex_dir = Path.home() / ".codex"
    print()
    print("No agent history was found at the default locations:")
    if source in ("all", "claude"):
        print(f"  - Claude Code: {claude_dir} (not found)")
    if source in ("all", "codex"):
        print(f"  - Codex:       {codex_dir} (not found)")
    print()
    print("What to try next:")
    print("  1. If you have not yet used Claude Code or Codex on this machine,")
    print("     start an agent session first, then rerun `ai-agents-metrics history-update`.")
    print("  2. If your agent history is in a non-default location, point to it:")
    print("       ai-agents-metrics history-update --claude-root /path/to/.claude")
    print("       ai-agents-metrics history-update --codex-state-path /path/to/.codex")
    print("  3. To scan only one source at a time:")
    print("       ai-agents-metrics history-update --source claude")
    print("       ai-agents-metrics history-update --source codex")


def _summarise_ingest_results(
    source: str,
    ingest_results: dict[str, IngestSummary],
    ingest_skipped: list[str],
    *,
    cli_module: CommandRuntime,
    json_output: bool,
) -> dict[str, object]:
    """Print per-source ingest output (or collect JSON payloads) and return the JSON dict."""
    ingest_summaries: dict[str, object] = {}
    if source == "all":
        for src_name in ingest_skipped:
            if not json_output:
                print(f"==> history-ingest ({src_name}) [skipped: {Path.home() / ('.' + src_name)} not found]")
        for src_name, ingest_summary in ingest_results.items():
            if not json_output:
                print(f"==> history-ingest ({src_name})")
                print(f"    Imported {ingest_summary.imported_files} files, {ingest_summary.threads} threads")
            else:
                ingest_summaries[src_name] = json.loads(cli_module.render_ingest_summary_json(ingest_summary))
    else:
        ingest_summary = next(iter(ingest_results.values()))
        if not json_output:
            print("==> history-ingest")
            print(f"    Imported {ingest_summary.imported_files} files, {ingest_summary.threads} threads")
        else:
            ingest_summaries = {source: json.loads(cli_module.render_ingest_summary_json(ingest_summary))}
    return ingest_summaries


def handle_audit_history(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_history(data)
    if getattr(args, "json", False):
        print(cli_module.render_audit_report_json(report))
    else:
        print(cli_module.render_audit_report(report))
    return 0


def handle_compare_metrics_to_history(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    warehouse_path = Path(args.warehouse_path).expanduser()
    cwd = Path(args.cwd).expanduser()
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.compare_metrics_to_history(
        data,
        warehouse_path=warehouse_path,
        cwd=cwd,
        metrics_path=metrics_path,
    )
    if getattr(args, "json", False):
        print(cli_module.render_history_compare_report_json(report))
    else:
        print(cli_module.render_history_compare_report(report))
    return 0


def handle_ingest_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    source_root_arg: str | None = getattr(args, "source_root", None)
    source: str = getattr(args, "source", None) or ("codex" if source_root_arg is not None else "all")
    json_output: bool = getattr(args, "json", False)
    warehouse_path = Path(args.warehouse_path).expanduser()

    summaries, skipped, error = _run_ingest(source, source_root_arg, warehouse_path, cli_module)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if source == "all":
        if json_output:
            print(json.dumps({k: json.loads(cli_module.render_ingest_summary_json(v)) for k, v in summaries.items()}))
        else:
            for src_name in skipped:
                print(f"Skipping {src_name}: {Path.home() / ('.' + src_name)} not found")
            for src_name, summary in summaries.items():
                print(f"[{src_name}] Ingested into {summary.warehouse_path}")
                print(f"  Source root: {summary.source_root}")
                print(f"  Scanned files: {summary.scanned_files}")
                print(f"  Imported files: {summary.imported_files}")
                print(f"  Skipped files: {summary.skipped_files}")
                print(f"  Projects: {summary.projects}")
                print(f"  Threads: {summary.threads}")
                print(f"  Sessions: {summary.sessions}")
                print(f"  Session events: {summary.session_events}")
                print(f"  Token usage events: {summary.token_usage_events}")
                print(f"  Total tokens: {summary.total_tokens}")
                print(f"  Messages: {summary.messages}")
        return 0

    summary = next(iter(summaries.values()))
    if json_output:
        print(cli_module.render_ingest_summary_json(summary))
    else:
        print(f"Ingested Codex history into {summary.warehouse_path}")
        print(f"Source root: {summary.source_root}")
        print(f"Scanned files: {summary.scanned_files}")
        print(f"Imported files: {summary.imported_files}")
        print(f"Skipped files: {summary.skipped_files}")
        print(f"Projects: {summary.projects}")
        print(f"Threads: {summary.threads}")
        print(f"Sessions: {summary.sessions}")
        print(f"Session events: {summary.session_events}")
        print(f"Token count events: {summary.token_count_events}")
        print(f"Token usage events: {summary.token_usage_events}")
        print(f"Input tokens: {summary.input_tokens}")
        print(f"Cached input tokens: {summary.cached_input_tokens}")
        print(f"Output tokens: {summary.output_tokens}")
        print(f"Reasoning output tokens: {summary.reasoning_output_tokens}")
        print(f"Total tokens: {summary.total_tokens}")
        print(f"Messages: {summary.messages}")
        print(f"Logs: {summary.logs}")
    return 0


def handle_normalize_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.normalize_codex_history(warehouse_path)
    if getattr(args, "json", False):
        print(cli_module.render_normalize_summary_json(summary))
    else:
        print(f"Normalized Codex history in {summary.warehouse_path}")
        print(f"Projects: {summary.projects}")
        print(f"Threads: {summary.threads}")
        print(f"Sessions: {summary.sessions}")
        print(f"Messages: {summary.messages}")
        print(f"Usage events: {summary.usage_events}")
        print(f"Logs: {summary.logs}")
    return 0


def handle_classify_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.classify_codex_history(warehouse_path)
    if getattr(args, "json", False):
        print(cli_module.render_classify_summary_json(summary))
    else:
        print(f"Classified session kinds in {summary.warehouse_path}")
        print(f"Classifier version: {summary.classifier_version}")
        print(f"Sessions total: {summary.sessions_total}")
        print(f"Main sessions: {summary.main_sessions}")
        print(f"Subagent sessions: {summary.subagent_sessions}")
        print(f"Unknown sessions: {summary.unknown_sessions}")
        if summary.practice_event_classifier_version:
            print(f"Practice events: {summary.practice_events_total}")
            if summary.practice_events_by_family:
                families = ", ".join(f"{family}={count}" for family, count in summary.practice_events_by_family)
                print(f"Practice events by family: {families}")
    return 0


def handle_derive_codex_history(args: Namespace, cli_module: CommandRuntime) -> int:
    warehouse_path = Path(args.warehouse_path).expanduser()
    with cli_module.metrics_mutation_lock(warehouse_path):
        summary = cli_module.derive_codex_history(warehouse_path)
    if getattr(args, "json", False):
        print(cli_module.render_derive_summary_json(summary))
    else:
        print(f"Derived Codex history in {summary.warehouse_path}")
        print(f"Projects: {summary.projects}")
        print(f"Goals: {summary.goals}")
        print(f"Attempts: {summary.attempts}")
        print(f"Timeline events: {summary.timeline_events}")
        print(f"Retry chains: {summary.retry_chains}")
        print(f"Message facts: {summary.message_facts}")
        print(f"Session usage: {summary.session_usage}")
        print(f"Token coverage: {summary.token_covered_sessions}/{summary.session_usage} sessions")
    return 0


def handle_history_update(args: Namespace, cli_module: CommandRuntime) -> int:
    """Run the full history pipeline: ingest → normalize → derive."""
    source_root_arg: str | None = getattr(args, "source_root", None)
    source: str = getattr(args, "source", None) or ("codex" if source_root_arg is not None else "all")
    warehouse_path = Path(args.warehouse_path).expanduser()
    json_output: bool = getattr(args, "json", False)

    ingest_results, ingest_skipped, error = _run_ingest(source, source_root_arg, warehouse_path, cli_module)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    ingest_summaries = _summarise_ingest_results(
        source, ingest_results, ingest_skipped, cli_module=cli_module, json_output=json_output
    )

    if not ingest_results and not warehouse_path.exists():
        if not json_output:
            _print_empty_history_guidance(source)
        else:
            print(json.dumps({"ingest": ingest_summaries, "normalize": None, "derive": None}))
        return 0


    if not json_output:
        print("==> history-normalize")
    with cli_module.metrics_mutation_lock(warehouse_path):
        normalize_summary = cli_module.normalize_codex_history(warehouse_path)
    if not json_output:
        print(f"    {normalize_summary.threads} threads, {normalize_summary.messages} messages")
        print("==> history-classify")
    with cli_module.metrics_mutation_lock(warehouse_path):
        classify_summary = cli_module.classify_codex_history(warehouse_path)
    if not json_output:
        print(
            f"    {classify_summary.main_sessions} main, {classify_summary.subagent_sessions} subagent, "
            f"{classify_summary.unknown_sessions} unknown"
        )
        if classify_summary.practice_event_classifier_version:
            print(f"    {classify_summary.practice_events_total} practice events")
        print("==> history-derive")
    with cli_module.metrics_mutation_lock(warehouse_path):
        derive_summary = cli_module.derive_codex_history(warehouse_path)
    if not json_output:
        print(f"    {derive_summary.goals} goals, {derive_summary.retry_chains} retry chains")
        print(f"Done. Warehouse: {warehouse_path}")
    else:
        print(
            json.dumps(
                {
                    "ingest": ingest_summaries,
                    "normalize": json.loads(cli_module.render_normalize_summary_json(normalize_summary)),
                    "classify": json.loads(cli_module.render_classify_summary_json(classify_summary)),
                    "derive": json.loads(cli_module.render_derive_summary_json(derive_summary)),
                }
            )
        )
    return 0


def handle_derive_retro_timeline(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    warehouse_path = Path(args.warehouse_path).expanduser()
    cwd = Path(args.cwd).expanduser()
    data = cli_module.load_metrics(metrics_path)
    cli_module.recompute_summary(data)
    with cli_module.metrics_mutation_lock(warehouse_path):
        report = cli_module.derive_retro_timeline(
            data,
            warehouse_path=warehouse_path,
            cwd=cwd,
            metrics_path=metrics_path,
            window_size=args.window_size,
        )
    if getattr(args, "json", False):
        print(cli_module.render_retro_timeline_report_json(report))
    else:
        print(cli_module.render_retro_timeline_report(report))
    return 0


def handle_audit_cost_coverage(args: Namespace, cli_module: CommandRuntime) -> int:
    metrics_path = Path(args.metrics_path)
    pricing_path = cli_module.resolve_effective_pricing_path(
        cwd=Path.cwd(),
        pricing_path=Path(args.pricing_path) if args.pricing_path else None,
    )
    codex_state_path = Path(args.codex_state_path)
    codex_logs_path = Path(args.codex_logs_path)
    claude_root = Path(args.claude_root) if getattr(args, "claude_root", None) is not None else Path.home() / ".claude"
    data = cli_module.load_metrics(metrics_path)
    report = cli_module.audit_cost_coverage(
        data,
        pricing_path=pricing_path,
        codex_state_path=codex_state_path,
        codex_logs_path=codex_logs_path,
        codex_thread_id=args.codex_thread_id,
        cwd=Path.cwd(),
        claude_root=claude_root,
    )
    if getattr(args, "json", False):
        print(cli_module.render_cost_audit_report_json(report))
    else:
        print(render_cost_audit_report(report))
    return 0
