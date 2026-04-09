from __future__ import annotations

import argparse


def _option_strings(parser: argparse.ArgumentParser) -> list[str]:
    options: list[str] = []
    for action in parser._actions:
        for option in action.option_strings:
            if option not in options:
                options.append(option)
    return options


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction[argparse.ArgumentParser] | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _shell_choices_for_completion(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if action.dest != "shell":
            continue
        if action.choices is None:
            return []
        return [str(choice) for choice in action.choices]
    return []


def _escape_single_quotes(value: str) -> str:
    return value.replace("'", "'\"'\"'")


def render_bash_completion(parser: argparse.ArgumentParser) -> str:
    subparsers_action = _subparsers_action(parser)
    if subparsers_action is None:
        raise ValueError("Parser does not define subcommands")

    command_names = list(subparsers_action.choices.keys())
    command_options = {
        name: _option_strings(subparser)
        for name, subparser in subparsers_action.choices.items()
    }
    completion_shells = _shell_choices_for_completion(subparsers_action.choices["completion"])

    lines = [
        "_ai_agents_metrics_completion() {",
        "  local cur cmd",
        "  cur=\"${COMP_WORDS[COMP_CWORD]}\"",
        "  cmd=\"${COMP_WORDS[1]}\"",
        "",
        "  if [[ ${COMP_CWORD} -eq 1 ]]; then",
        f"    COMPREPLY=( $(compgen -W '{' '.join(command_names)}' -- \"$cur\") )",
        "    return",
        "  fi",
        "",
        "  case \"$cmd\" in",
    ]

    for command_name, options in command_options.items():
        option_words = options[:]
        if command_name == "completion":
            option_words.extend(completion_shells)
        joined = " ".join(option_words)
        lines.extend(
            [
                f"    {command_name})",
                f"      COMPREPLY=( $(compgen -W '{joined}' -- \"$cur\") )",
                "      return",
                "      ;;",
            ]
        )

    lines.extend(
        [
            "  esac",
            "",
            "  COMPREPLY=()",
            "}",
            "",
            "complete -F _ai_agents_metrics_completion ai-agents-metrics",
            "complete -F _ai_agents_metrics_completion codex-metrics",
            "",
        ]
    )
    return "\n".join(lines)


def render_zsh_completion(parser: argparse.ArgumentParser) -> str:
    subparsers_action = _subparsers_action(parser)
    if subparsers_action is None:
        raise ValueError("Parser does not define subcommands")

    command_names = list(subparsers_action.choices.keys())
    command_options = {
        name: _option_strings(subparser)
        for name, subparser in subparsers_action.choices.items()
    }
    completion_shells = _shell_choices_for_completion(subparsers_action.choices["completion"])

    lines = [
        "#compdef codex-metrics",
        "",
        "local curcontext=\"$curcontext\" state line",
        "typeset -A opt_args",
        "",
        "local -a commands",
        "commands=(",
    ]
    lines.extend([f"  '{name}:{name} command'" for name in command_names])
    lines.extend(
        [
            ")",
            "",
            "_arguments -C \\",
            "  '-h[show help]' \\",
            "  '--help[show help]' \\",
            "  '1:command:->command' \\",
            "  '*::args:->args'",
            "",
            "case $state in",
            "  command)",
            "    _describe 'command' commands",
            "    ;;",
            "  args)",
            "    case \"$words[2]\" in",
        ]
    )

    for command_name, options in command_options.items():
        lines.append(f"      {command_name})")
        option_lines = [
            f"          '{option}[{option}]' \\\n" for option in options if option not in {"-h", "--help"}
        ]
        option_lines.insert(0, "          '--help[show help]' \\\n")
        option_lines.insert(0, "          '-h[show help]' \\\n")
        if command_name == "completion":
            option_lines.append(
                f"          '1:shell:({' '.join(completion_shells)})' \\\n"
            )
        lines.append("        _arguments \\")
        for option_line in option_lines[:-1]:
            lines.append(option_line.rstrip())
        if option_lines:
            lines.append(option_lines[-1].rstrip(" \\\n"))
        lines.extend(
            [
                "        ;;",
            ]
        )

    lines.extend(
        [
            "    esac",
            "    ;;",
            "esac",
            "",
        ]
    )
    return "\n".join(lines)


def render_completion(parser: argparse.ArgumentParser, shell: str) -> str:
    if shell == "bash":
        return render_bash_completion(parser)
    if shell == "zsh":
        return render_zsh_completion(parser)
    raise ValueError(f"Unsupported shell: {shell}")
