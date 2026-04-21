"""Repository scaffolding: metrics artifact, policy doc, and instructions-file block."""
from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Protocol

from ai_agents_metrics.storage import atomic_write_text, ensure_parent_dir

START_MARKER = "<!-- ai-agents-metrics:start -->"
END_MARKER = "<!-- ai-agents-metrics:end -->"


@dataclass(frozen=True)
class BootstrapResult:
    messages: list[str]


class DefaultMetricsCallable(Protocol):
    def __call__(self) -> dict[str, object]: ...


class LoadMetricsCallable(Protocol):
    def __call__(self, path: Path) -> dict[str, object]: ...


class SaveReportCallable(Protocol):
    def __call__(self, path: Path, data: dict[str, object]) -> None: ...


@dataclass(frozen=True)
class BootstrapPaths:
    """Target paths for a bootstrap run — grouped so helpers stay under the arg cap."""

    metrics_path: Path
    report_path: Path | None
    policy_path: Path
    command_path: Path
    agents_path: Path


@dataclass(frozen=True)
class BootstrapCallbacks:
    """Pluggable metrics/report callables — kept together to shrink helper signatures."""

    load_metrics: LoadMetricsCallable
    default_metrics: DefaultMetricsCallable
    save_report: SaveReportCallable


# BootstrapPlan aggregates per-flag decisions consumed by bootstrap_project.
# Each field is a distinct write/replace intent, so compressing them would
# obscure what the plan approves.
@dataclass(frozen=True)
class BootstrapPlan:  # pylint: disable=too-many-instance-attributes
    metrics_data: dict[str, object]
    policy_content: str
    agents_text: str
    create_metrics: bool
    create_report: bool
    replace_report: bool
    create_policy: bool
    replace_policy: bool
    policy_conflict: bool
    create_agents: bool
    write_agents: bool


def load_policy_template() -> str:
    return resources.files("ai_agents_metrics").joinpath("data/bootstrap_codex_metrics_policy.md").read_text(
        encoding="utf-8"
    )


def path_for_agents(target_path: Path, *, agents_path: Path) -> Path:
    return Path(os.path.relpath(target_path, start=agents_path.parent))


def render_agents_block(
    *,
    policy_path: Path,
    command_path: Path,
    metrics_path: Path,
    report_path: Path,
    instructions_filename: str,
) -> str:
    policy_label = policy_path.as_posix()
    command_label = command_path.as_posix()
    del metrics_path
    del report_path
    return (
        f"{START_MARKER}\n"
        "## AI Agents Metrics\n\n"
        "### Read first\n\n"
        "Before starting or continuing any engineering task, always read:\n\n"
        f"- `{instructions_filename}`\n"
        f"- `{policy_label}`\n\n"
        f"Use `{command_label} ...` in this repository.\n\n"
        f"If `{command_label}` is unavailable, stop and report an installation or invocation mismatch before proceeding.\n\n"
        f"The rules in `{policy_label}` are mandatory and are part of this repository's operating instructions.\n\n"
        f"{END_MARKER}\n"
    )


def upsert_agents_text(
    existing_text: str | None,
    *,
    policy_path: Path,
    command_path: Path,
    metrics_path: Path,
    report_path: Path,
    instructions_filename: str,
) -> tuple[str, str]:
    block = render_agents_block(
        policy_path=policy_path,
        command_path=command_path,
        metrics_path=metrics_path,
        report_path=report_path,
        instructions_filename=instructions_filename,
    )
    if existing_text is None:
        return f"# {instructions_filename}\n\n{block}", "create"

    if START_MARKER in existing_text and END_MARKER in existing_text:
        start_index = existing_text.index(START_MARKER)
        end_index = existing_text.index(END_MARKER) + len(END_MARKER)
        replaced = existing_text[:start_index].rstrip()
        suffix = existing_text[end_index:].lstrip("\n")
        updated_parts = [part for part in (replaced, block.rstrip(), suffix.rstrip()) if part]
        return "\n\n".join(updated_parts) + "\n", "update"

    stripped = existing_text.rstrip()
    if not stripped:
        return f"# {instructions_filename}\n\n{block}", "create"
    return f"{stripped}\n\n{block}", "append"


def write_path(path: Path, content: str) -> None:
    ensure_parent_dir(path)
    atomic_write_text(path, content)


def build_bootstrap_plan(
    *,
    paths: BootstrapPaths,
    force: bool,
    dry_run: bool,
    callbacks: BootstrapCallbacks,
) -> BootstrapPlan:
    if paths.metrics_path.exists():
        metrics_data = callbacks.load_metrics(paths.metrics_path)
    else:
        metrics_data = callbacks.default_metrics()

    policy_content = load_policy_template()
    policy_conflict = False
    if paths.policy_path.exists():
        existing_policy = paths.policy_path.read_text(encoding="utf-8")
        if existing_policy != policy_content and not force:
            if not dry_run:
                raise ValueError(
                    f"Policy file already exists with different content: {paths.policy_path}. Use --force to replace it."
                )
            policy_conflict = True
        replace_policy = existing_policy != policy_content and not policy_conflict
        create_policy = False
    else:
        create_policy = True
        replace_policy = False

    existing_agents_text = paths.agents_path.read_text(encoding="utf-8") if paths.agents_path.exists() else None
    agents_text, _agents_action = upsert_agents_text(
        existing_agents_text,
        policy_path=path_for_agents(paths.policy_path, agents_path=paths.agents_path),
        command_path=path_for_agents(paths.command_path, agents_path=paths.agents_path),
        metrics_path=path_for_agents(paths.metrics_path, agents_path=paths.agents_path),
        report_path=(
            path_for_agents(paths.report_path, agents_path=paths.agents_path)
            if paths.report_path is not None
            else Path("docs/ai-agents-metrics.md")
        ),
        instructions_filename=paths.agents_path.name,
    )

    create_metrics = not paths.metrics_path.exists()
    create_report = paths.report_path is not None and not paths.report_path.exists()
    replace_report = (
        paths.report_path is not None
        and paths.metrics_path.exists() is False
        and paths.report_path.exists()
    )

    return BootstrapPlan(
        metrics_data=metrics_data,
        policy_content=policy_content,
        agents_text=agents_text,
        create_metrics=create_metrics,
        create_report=create_report,
        replace_report=replace_report,
        create_policy=create_policy,
        replace_policy=replace_policy,
        policy_conflict=policy_conflict,
        create_agents=existing_agents_text is None,
        write_agents=existing_agents_text != agents_text,
    )


def _dry_run_messages(plan: BootstrapPlan, paths: BootstrapPaths) -> list[str]:
    messages: list[str] = []
    if paths.report_path is None:
        messages.append(
            "Would skip markdown report generation by default (use render-report or --write-report when needed)"
        )
    elif plan.create_report:
        messages.append(f"Would create report file: {paths.report_path}")
    elif plan.replace_report:
        messages.append(f"Would replace report file: {paths.report_path}")
    else:
        messages.append(f"Would keep existing report file: {paths.report_path}")

    if plan.create_policy:
        messages.append(f"Would create policy file: {paths.policy_path}")
    elif plan.policy_conflict:
        messages.append(
            f"Would refuse to replace existing policy file without --force: {paths.policy_path}"
        )
    elif plan.replace_policy:
        messages.append(f"Would replace policy file: {paths.policy_path}")
    else:
        messages.append(f"Would keep existing policy file: {paths.policy_path}")

    if not paths.agents_path.exists():
        messages.append(f"Would create instructions file: {paths.agents_path}")
    elif plan.write_agents:
        messages.append(f"Would update instructions file: {paths.agents_path}")
    else:
        messages.append(f"Would keep instructions file unchanged: {paths.agents_path}")
    return messages


def _apply_plan(
    plan: BootstrapPlan,
    paths: BootstrapPaths,
    save_report: SaveReportCallable,
) -> list[str]:
    messages: list[str] = []
    if plan.create_metrics:
        ensure_parent_dir(paths.metrics_path)
        if not paths.metrics_path.exists():
            paths.metrics_path.touch()

    if paths.report_path is None:
        messages.append("Skipping markdown report generation by default")
    elif plan.create_report or plan.replace_report:
        save_report(paths.report_path, plan.metrics_data)
        verb = "Created" if plan.create_report else "Replaced"
        messages.append(f"{verb} report file: {paths.report_path}")
    else:
        messages.append(f"Keeping existing report file: {paths.report_path}")

    if plan.create_policy:
        write_path(paths.policy_path, plan.policy_content)
        messages.append(f"Created policy file: {paths.policy_path}")
    elif plan.replace_policy:
        write_path(paths.policy_path, plan.policy_content)
        messages.append(f"Replaced policy file: {paths.policy_path}")
    else:
        messages.append(f"Keeping existing policy file: {paths.policy_path}")

    if plan.write_agents:
        write_path(paths.agents_path, plan.agents_text)
        if plan.create_agents:
            messages.append(f"Created instructions file: {paths.agents_path}")
        else:
            messages.append(f"Updated instructions file: {paths.agents_path}")
    else:
        messages.append(f"Keeping instructions file unchanged: {paths.agents_path}")
    return messages


def bootstrap_project(
    *,
    paths: BootstrapPaths,
    force: bool,
    dry_run: bool,
    callbacks: BootstrapCallbacks,
) -> BootstrapResult:
    plan = build_bootstrap_plan(
        paths=paths,
        force=force,
        dry_run=dry_run,
        callbacks=callbacks,
    )
    messages: list[str] = []

    if plan.create_metrics:
        messages.append(f"{'Would create' if dry_run else 'Created'} metrics file: {paths.metrics_path}")
    else:
        messages.append(f"{'Would keep' if dry_run else 'Keeping'} existing metrics file: {paths.metrics_path}")

    if dry_run:
        messages.extend(_dry_run_messages(plan, paths))
    else:
        messages.extend(_apply_plan(plan, paths, callbacks.save_report))

    return BootstrapResult(messages=messages)
