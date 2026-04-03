from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

LINEAR_COMMIT_SUBJECT_RE = re.compile(r"^CODEX-\d+: .+\S$")
NO_TASK_COMMIT_SUBJECT_RE = re.compile(r"^NO-TASK: .+\S$")


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


def validate_commit_subject(subject: str) -> CommitMessageValidationResult:
    normalized_subject = subject.strip()
    if not normalized_subject:
        return CommitMessageValidationResult(
            allowed=False,
            reason="Commit subject is empty. Use CODEX-123: summary or NO-TASK: summary.",
        )
    if normalized_subject.startswith("Merge ") or normalized_subject.startswith("Revert "):
        return CommitMessageValidationResult(allowed=True)
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


def validate_commit_message_text(message_text: str) -> CommitMessageValidationResult:
    return validate_commit_subject(_subject_from_message_text(message_text))


def validate_commit_message_file(path: Path) -> CommitMessageValidationResult:
    return validate_commit_message_text(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m codex_metrics.commit_message <commit-message-file>", file=sys.stderr)
        return 2

    result = validate_commit_message_file(Path(args[0]))
    if result.allowed:
        return 0

    print(result.reason, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
