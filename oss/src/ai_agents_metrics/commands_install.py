"""Installer and bootstrap command handlers for ai-agents-metrics."""
from __future__ import annotations

import os
import shutil
import stat
import sys
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING

from ai_agents_metrics.storage import metrics_mutation_lock

if TYPE_CHECKING:
    from ai_agents_metrics.commands import CommandRuntime


def _resolve_invocation_path() -> Path:
    argv0 = Path(sys.argv[0])
    if argv0.is_absolute() or argv0.parent != Path("."):
        return argv0.resolve()

    discovered = shutil.which(sys.argv[0])
    if discovered is not None:
        return Path(discovered).resolve()

    return argv0.resolve()


def _path_dir_is_available(target_dir: Path) -> bool:
    normalized_target = target_dir.expanduser().resolve(strict=False)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        if Path(entry).expanduser().resolve(strict=False) == normalized_target:
            return True
    return False


def _shell_path_snippet(target_dir: Path) -> tuple[str, str]:
    shell_name = Path(os.environ.get("SHELL", "")).name
    rendered_dir = str(target_dir.expanduser())
    export_line = f'export PATH="{rendered_dir}:$PATH"'
    if shell_name == "zsh":
        return "~/.zshrc", export_line
    if shell_name == "bash":
        return "~/.bashrc", export_line
    return "your shell profile", export_line


def _shell_profile_path() -> Path | None:
    shell_name = Path(os.environ.get("SHELL", "")).name
    home = Path.home()
    if shell_name == "zsh":
        return home / ".zshrc"
    if shell_name == "bash":
        return home / ".bashrc"
    return None


def _ensure_profile_has_path_line(profile_path: Path, export_line: str) -> bool:
    if profile_path.exists():
        existing_text = profile_path.read_text(encoding="utf-8")
    else:
        existing_text = ""
    if export_line in existing_text:
        return False

    updated = existing_text.rstrip("\n")
    if updated:
        updated += "\n"
    updated += f"{export_line}\n"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(updated, encoding="utf-8")
    return True


def _detect_shadowing_command(*, command_name: str, target_path: Path) -> Path | None:
    resolved_on_path = shutil.which(command_name)
    if resolved_on_path is None:
        return None

    resolved_path = Path(resolved_on_path).expanduser().resolve(strict=False)
    if resolved_path == target_path.expanduser().resolve(strict=False):
        return None

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env is None:
        return None

    venv_path = Path(virtual_env).expanduser().resolve(strict=False)
    try:
        resolved_path.relative_to(venv_path)
    except ValueError:
        return None
    return resolved_path


def _write_python_launcher(target_path: Path, *, python_executable: Path, source_path: Path) -> None:
    launcher = (
        "#!/bin/sh\n"
        f"exec '{python_executable}' '{source_path}' \"$@\"\n"
    )
    target_path.write_text(launcher, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_source_module_launcher(target_path: Path, *, python_executable: Path, source_root: Path) -> None:
    launcher = (
        "#!/bin/sh\n"
        "if [ -n \"$PYTHONPATH\" ]; then\n"
        f"  export PYTHONPATH='{source_root}':\"$PYTHONPATH\"\n"
        "else\n"
        f"  export PYTHONPATH='{source_root}'\n"
        "fi\n"
        f"exec '{python_executable}' -m ai_agents_metrics \"$@\"\n"
    )
    target_path.write_text(launcher, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _render_python_launcher(*, python_executable: Path, source_path: Path, repo_root: Path) -> str:
    return (
        "#!/bin/sh\n"
        f"cd '{repo_root}' || exit 1\n"
        f"exec '{python_executable}' '{source_path}' \"$@\"\n"
    )


def _render_source_module_launcher(*, python_executable: Path, source_root: Path, repo_root: Path) -> str:
    return (
        "#!/bin/sh\n"
        f"cd '{repo_root}' || exit 1\n"
        "if [ -n \"$PYTHONPATH\" ]; then\n"
        f"  export PYTHONPATH='{source_root}':\"$PYTHONPATH\"\n"
        "else\n"
        f"  export PYTHONPATH='{source_root}'\n"
        "fi\n"
        f"exec '{python_executable}' -m ai_agents_metrics \"$@\"\n"
    )


def _render_repo_local_wrapper(source_path: Path, repo_root: Path) -> str:
    if source_path.suffix == ".py" and source_path.name == "__main__.py":
        return _render_source_module_launcher(
            python_executable=Path(sys.executable),
            source_root=source_path.parents[1],
            repo_root=repo_root,
        )
    if source_path.suffix == ".py":
        return _render_python_launcher(
            python_executable=Path(sys.executable),
            source_path=source_path,
            repo_root=repo_root,
        )
    return "#!/bin/sh\n" f"cd '{repo_root}' || exit 1\n" f"exec '{source_path}' \"$@\"\n"


def _write_repo_local_wrapper(target_path: Path, source_path: Path, repo_root: Path) -> str:
    content = _render_repo_local_wrapper(source_path, repo_root)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    target_path.chmod(target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return content


def handle_install_self(args: Namespace, _cli_module: CommandRuntime) -> int:
    source_path = _resolve_invocation_path()
    target_path = Path(args.target_path) if args.target_path else Path(args.target_dir) / args.command_name

    if source_path == target_path.resolve(strict=False):
        print(f"Already installed at {target_path}")
        shadowing_path = _detect_shadowing_command(command_name=args.command_name, target_path=target_path)
        if shadowing_path is not None:
            print(
                f"Warning: active virtualenv is shadowing the global install via {shadowing_path}. "
                f"Use {target_path} explicitly or deactivate the virtualenv before relying on `{args.command_name}`."
            )
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() or target_path.is_symlink():
        if target_path.is_dir() and not target_path.is_symlink():
            raise ValueError(f"Install target is a directory: {target_path}")
        target_path.unlink()

    launcher_mode = source_path.suffix == ".py" and os.name != "nt"
    use_copy = (args.copy or os.name == "nt") and not launcher_mode
    if launcher_mode and source_path.name == "__main__.py":
        _write_source_module_launcher(
            target_path,
            python_executable=Path(sys.executable),
            source_root=source_path.parents[1],
        )
        verb = "Installed launcher"
    elif launcher_mode:
        _write_python_launcher(target_path, python_executable=Path(sys.executable), source_path=source_path)
        verb = "Installed launcher"
    elif use_copy:
        shutil.copy2(source_path, target_path)
        mode = source_path.stat().st_mode
        target_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        verb = "Copied"
    else:
        target_path.symlink_to(source_path)
        verb = "Linked"

    print(f"{verb} {source_path} -> {target_path}")
    if not _path_dir_is_available(target_path.parent):
        profile_name, export_line = _shell_path_snippet(target_path.parent)
        profile_path = _shell_profile_path()
        if args.write_shell_profile:
            if profile_path is None:
                raise ValueError("Cannot determine shell profile automatically for this shell; add PATH manually.")
            changed = _ensure_profile_has_path_line(profile_path, export_line)
            if changed:
                print(f"Added PATH update to {profile_path}")
            else:
                print(f"PATH update already present in {profile_path}")
        else:
            print(f"Warning: {target_path.parent.expanduser()} is not on PATH.")
            print(f"Add this line to {profile_name}:")
            print(export_line)
        print("Then reopen your shell before running `ai-agents-metrics` by command name.")
    shadowing_path = _detect_shadowing_command(command_name=args.command_name, target_path=target_path)
    if shadowing_path is not None:
        print(
            f"Warning: active virtualenv is shadowing the global install via {shadowing_path}. "
            f"Use {target_path} explicitly or deactivate the virtualenv before relying on `{args.command_name}`."
        )
    return 0


def handle_bootstrap(args: Namespace, cli_module: CommandRuntime) -> int:
    target_dir = Path(args.target_dir)

    def resolve_target_path(raw_path: str) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else target_dir / path

    metrics_path = resolve_target_path(args.metrics_path)
    report_path = resolve_target_path(args.report_path) if getattr(args, "write_report", False) else None
    policy_path = resolve_target_path(args.policy_path)
    command_path = resolve_target_path(args.command_path)
    agents_path = resolve_target_path(args.agents_path)
    source_path = _resolve_invocation_path()
    wrapper_content = _render_repo_local_wrapper(source_path, target_dir.resolve())
    wrapper_exists = command_path.exists()
    wrapper_matches = wrapper_exists and command_path.read_text(encoding="utf-8") == wrapper_content

    with metrics_mutation_lock(metrics_path):
        messages = cli_module.bootstrap_project(
            target_dir=target_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            policy_path=policy_path,
            command_path=command_path,
            agents_path=agents_path,
            force=args.force,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            if not wrapper_exists:
                messages.append(f"Would create command wrapper: {command_path}")
            elif wrapper_matches:
                messages.append(f"Would keep command wrapper: {command_path}")
            else:
                messages.append(f"Would update command wrapper: {command_path}")
        else:
            if not wrapper_exists:
                _write_repo_local_wrapper(command_path, source_path, target_dir.resolve())
                messages.append(f"Created command wrapper: {command_path}")
            elif wrapper_matches:
                messages.append(f"Keeping command wrapper: {command_path}")
            else:
                _write_repo_local_wrapper(command_path, source_path, target_dir.resolve())
                messages.append(f"Updated command wrapper: {command_path}")

    for message in messages:
        print(message)
    return 0
