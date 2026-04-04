from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class PublicBoundaryRules:
    allowed_roots: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    forbidden_globs: tuple[str, ...]
    forbidden_extensions: tuple[str, ...]
    forbidden_literal_markers: tuple[str, ...]
    forbidden_regex_markers: tuple[str, ...]
    ignored_paths: tuple[str, ...]
    marker_ignored_paths: tuple[str, ...]


@dataclass(frozen=True)
class PublicBoundaryFinding:
    kind: str
    path: str
    message: str
    matched_rule: str
    line: int | None = None


@dataclass(frozen=True)
class PublicBoundaryReport:
    repo_root: Path
    rules_path: Path
    files_scanned: int
    findings: tuple[PublicBoundaryFinding, ...]


def load_public_boundary_rules(path: Path) -> PublicBoundaryRules:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return PublicBoundaryRules(
        allowed_roots=_normalize_rule_values(raw.get("allowed_roots", [])),
        forbidden_paths=_normalize_rule_values(raw.get("forbidden_paths", [])),
        forbidden_globs=_normalize_rule_values(raw.get("forbidden_globs", [])),
        forbidden_extensions=_normalize_rule_values(raw.get("forbidden_extensions", []), lower=True),
        forbidden_literal_markers=_normalize_rule_values(raw.get("forbidden_literal_markers", [])),
        forbidden_regex_markers=_normalize_rule_values(raw.get("forbidden_regex_markers", [])),
        ignored_paths=_normalize_rule_values(raw.get("ignored_paths", [])),
        marker_ignored_paths=_normalize_rule_values(raw.get("marker_ignored_paths", [])),
    )


def _normalize_rule_values(values: object, *, lower: bool = False) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise ValueError("public boundary rule values must be lists")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("public boundary rules must contain only strings")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("public boundary rules must not contain empty strings")
        normalized.append(cleaned.lower() if lower else cleaned)
    return tuple(normalized)


def verify_public_boundary(*, repo_root: Path, rules_path: Path) -> PublicBoundaryReport:
    normalized_root = repo_root.resolve()
    normalized_rules = rules_path.resolve()
    rules = load_public_boundary_rules(normalized_rules)
    candidate_paths = _collect_candidate_paths(normalized_root, rules)
    skipped_marker_paths: set[str] = set()
    try:
        skipped_marker_paths.add(normalized_rules.relative_to(normalized_root).as_posix())
    except ValueError:
        pass
    for pattern in rules.marker_ignored_paths:
        for path_text in candidate_paths:
            if _glob_matches(path_text, pattern):
                skipped_marker_paths.add(path_text)
    findings: list[PublicBoundaryFinding] = []
    findings.extend(_check_allowed_roots(candidate_paths, rules))
    findings.extend(_check_forbidden_paths(candidate_paths, rules))
    findings.extend(_check_forbidden_extensions(candidate_paths, rules))
    findings.extend(
        _check_forbidden_markers(
            normalized_root,
            candidate_paths,
            rules,
            skipped_marker_paths=skipped_marker_paths,
        )
    )
    findings.sort(key=lambda finding: (finding.path, finding.kind, finding.line or 0, finding.matched_rule))
    return PublicBoundaryReport(
        repo_root=normalized_root,
        rules_path=normalized_rules,
        files_scanned=len(candidate_paths),
        findings=tuple(findings),
    )


def render_public_boundary_report(report: PublicBoundaryReport) -> str:
    if not report.findings:
        return (
            f"Public boundary verification passed: scanned {report.files_scanned} file(s) under "
            f"{report.repo_root} using {report.rules_path}."
        )

    lines = [
        (
            f"Public boundary verification failed: {len(report.findings)} finding(s) across "
            f"{report.files_scanned} scanned file(s)."
        )
    ]
    for finding in report.findings:
        location = finding.path
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(
            f"- [{finding.kind}] {location} | rule={finding.matched_rule} | {finding.message}"
        )
    return "\n".join(lines)


def render_public_boundary_report_json(report: PublicBoundaryReport) -> str:
    payload = {
        "repo_root": str(report.repo_root),
        "rules_path": str(report.rules_path),
        "files_scanned": report.files_scanned,
        "findings": [
            {
                "kind": finding.kind,
                "path": finding.path,
                "message": finding.message,
                "matched_rule": finding.matched_rule,
                "line": finding.line,
            }
            for finding in report.findings
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _collect_candidate_paths(repo_root: Path, rules: PublicBoundaryRules) -> list[str]:
    git_paths = _git_candidate_paths(repo_root)
    if git_paths is not None:
        return [path for path in git_paths if not _is_ignored_path(path, rules)]

    collected: list[str] = []
    for candidate in repo_root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(repo_root).as_posix()
        if _is_ignored_path(relative, rules):
            continue
        collected.append(relative)
    collected.sort()
    return collected


def _git_candidate_paths(repo_root: Path) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=repo_root,
            text=False,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    raw_paths = [item.decode("utf-8") for item in result.stdout.split(b"\x00") if item]
    normalized = sorted(_normalize_relative_path(path) for path in raw_paths if path)
    return normalized


def _normalize_relative_path(path_text: str) -> str:
    return PurePosixPath(path_text.strip()).as_posix()


def _is_ignored_path(path_text: str, rules: PublicBoundaryRules) -> bool:
    return any(_glob_matches(path_text, pattern) for pattern in rules.ignored_paths)


def _check_allowed_roots(paths: list[str], rules: PublicBoundaryRules) -> list[PublicBoundaryFinding]:
    findings: list[PublicBoundaryFinding] = []
    allowed = set(rules.allowed_roots)
    for path_text in paths:
        top_level = path_text.split("/", maxsplit=1)[0]
        if top_level not in allowed and path_text not in allowed:
            findings.append(
                PublicBoundaryFinding(
                    kind="unexpected_root",
                    path=path_text,
                    message=f"path is outside allowed public roots; top-level root `{top_level}` is not allowlisted",
                    matched_rule=top_level,
                )
            )
    return findings


def _check_forbidden_paths(paths: list[str], rules: PublicBoundaryRules) -> list[PublicBoundaryFinding]:
    findings: list[PublicBoundaryFinding] = []
    for path_text in paths:
        for forbidden in rules.forbidden_paths:
            if path_text == forbidden or path_text.startswith(f"{forbidden}/"):
                findings.append(
                    PublicBoundaryFinding(
                        kind="forbidden_path",
                        path=path_text,
                        message="path matches a forbidden private-only boundary rule",
                        matched_rule=forbidden,
                    )
                )
        for pattern in rules.forbidden_globs:
            if _glob_matches(path_text, pattern):
                findings.append(
                    PublicBoundaryFinding(
                        kind="forbidden_path",
                        path=path_text,
                        message="path matches a forbidden glob rule",
                        matched_rule=pattern,
                    )
                )
    return findings


def _check_forbidden_extensions(paths: list[str], rules: PublicBoundaryRules) -> list[PublicBoundaryFinding]:
    findings: list[PublicBoundaryFinding] = []
    forbidden_extensions = set(rules.forbidden_extensions)
    for path_text in paths:
        suffix = Path(path_text).suffix.lower()
        if suffix and suffix in forbidden_extensions:
            findings.append(
                PublicBoundaryFinding(
                    kind="forbidden_extension",
                    path=path_text,
                    message="file extension is not allowed in the public repository",
                    matched_rule=suffix,
                )
            )
    return findings


def _check_forbidden_markers(
    repo_root: Path,
    paths: list[str],
    rules: PublicBoundaryRules,
    *,
    skipped_marker_paths: set[str],
) -> list[PublicBoundaryFinding]:
    findings: list[PublicBoundaryFinding] = []
    regex_patterns = tuple(re.compile(pattern) for pattern in rules.forbidden_regex_markers)
    for path_text in paths:
        if path_text in skipped_marker_paths:
            continue
        text = _read_text_candidate(repo_root / path_text)
        if text is None:
            continue
        for literal in rules.forbidden_literal_markers:
            index = text.find(literal)
            if index == -1:
                continue
            findings.append(
                PublicBoundaryFinding(
                    kind="forbidden_marker",
                    path=path_text,
                    message="file contains a forbidden literal private-content marker",
                    matched_rule=literal,
                    line=_line_number_for_offset(text, index),
                )
            )
        for pattern in regex_patterns:
            match = pattern.search(text)
            if match is None:
                continue
            findings.append(
                PublicBoundaryFinding(
                    kind="forbidden_marker",
                    path=path_text,
                    message="file contains a forbidden regex private-content marker",
                    matched_rule=pattern.pattern,
                    line=_line_number_for_offset(text, match.start()),
                )
            )
    return findings


def _read_text_candidate(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _glob_matches(path_text: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path_text, pattern) or PurePosixPath(path_text).match(pattern)
