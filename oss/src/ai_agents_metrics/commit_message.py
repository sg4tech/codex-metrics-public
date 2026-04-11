from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LINEAR_COMMIT_SUBJECT_RE = re.compile(r"^CODEX-\d+: .+\S$")
NO_TASK_COMMIT_SUBJECT_RE = re.compile(r"^NO-TASK: .+\S$")
RETRO_ONLY_PATH_PREFIXES = ("docs/retros/",)


@dataclass(frozen=True)
class CommitMessageValidationResult:
    allowed: bool
    reason: str | None = None


def _subject_from_message_text(message_text: str) -> str:
    for line in message_text.splitlines():
        subject = line.strip()
        if not subject or subject.startswith("#"):
            continue
        return subject
    return ""


def _staged_paths(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_retro_only_commit(staged_paths: list[str]) -> bool:
    return bool(staged_paths) and all(path.startswith(RETRO_ONLY_PATH_PREFIXES) for path in staged_paths)


def validate_commit_subject(subject: str, staged_paths: list[str] | None = None) -> CommitMessageValidationResult:
    normalized_subject = subject.strip()
    if not normalized_subject:
        return CommitMessageValidationResult(
            allowed=False,
            reason="Commit subject is empty. Use CODEX-123: summary or NO-TASK: summary.",
        )
    if normalized_subject.startswith("Merge ") or normalized_subject.startswith("Revert "):
        return CommitMessageValidationResult(allowed=True)
    if staged_paths is not None and _is_retro_only_commit(staged_paths):
        if NO_TASK_COMMIT_SUBJECT_RE.fullmatch(normalized_subject):
            return CommitMessageValidationResult(allowed=True)
        return CommitMessageValidationResult(
            allowed=False,
            reason=(
                "Retrospective-only commits must use NO-TASK: summary. "
                "Do not use a Linear-linked subject when the staged changes are only in docs/retros/."
            ),
        )
    if LINEAR_COMMIT_SUBJECT_RE.fullmatch(normalized_subject):
        return CommitMessageValidationResult(allowed=True)
    if NO_TASK_COMMIT_SUBJECT_RE.fullmatch(normalized_subject):
        return CommitMessageValidationResult(allowed=True)
    return CommitMessageValidationResult(
        allowed=False,
        reason=(
            "Commit subject must match CODEX-123: summary or NO-TASK: summary. "
            "Use CODEX-123 for Linear-linked work and NO-TASK only for intentional taskless changes."
        ),
    )


def validate_commit_message_text(
    message_text: str, staged_paths: list[str] | None = None
) -> CommitMessageValidationResult:
    return validate_commit_subject(_subject_from_message_text(message_text), staged_paths=staged_paths)


def validate_commit_message_file(path: Path, repo_root: Path | None = None) -> CommitMessageValidationResult:
    effective_repo_root = repo_root if repo_root is not None else Path.cwd()
    return validate_commit_message_text(
        path.read_text(encoding="utf-8"),
        staged_paths=_staged_paths(effective_repo_root),
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m ai_agents_metrics.commit_message <commit-message-file>", file=sys.stderr)
        return 2

    result = validate_commit_message_file(Path(args[0]))
    if result.allowed:
        return 0

    print(result.reason, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
