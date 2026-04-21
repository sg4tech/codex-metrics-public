"""Staged-file security scanner: secrets, private keys, dangerous patterns."""
from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_SECURITY_RULES_PATH = Path("config/security-rules.toml")
SOURCE_AST_EXTENSIONS = {".py", ".pyi"}
CONFIG_HYGIENE_EXTENSIONS = {".conf", ".cfg", ".ini", ".json", ".properties", ".toml", ".yaml", ".yml"}
CONFIG_SECRET_KEYS = (
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "passwd",
    "password",
    "refresh_token",
    "secret",
    "token",
)
CONFIG_SECRET_PLACEHOLDERS = (
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "replace_me",
    "test",
    "your_",
)
CONFIG_SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        ["']?(?P<quoted_key>password|passwd|secret|token|api[_-]?key|client_secret|refresh_token|access_token)["']?
        |
        (?P<plain_key>password|passwd|secret|token|api[_-]?key|client_secret|refresh_token|access_token)
    )
    \s*[:=]\s*
    (?P<value>[^#;\n]+?)
    \s*$
    """
)


@dataclass(frozen=True)
class SecurityRules:
    forbidden_paths: tuple[str, ...]
    forbidden_globs: tuple[str, ...]
    forbidden_extensions: tuple[str, ...]
    forbidden_literal_markers: tuple[str, ...]
    forbidden_regex_markers: tuple[str, ...]
    ignored_paths: tuple[str, ...]
    marker_ignored_paths: tuple[str, ...]


@dataclass(frozen=True)
class SecurityFinding:
    kind: str
    path: str
    message: str
    matched_rule: str
    line: int | None = None


@dataclass(frozen=True)
class SecurityReport:
    repo_root: Path
    rules_path: Path
    files_scanned: int
    findings: tuple[SecurityFinding, ...]


def load_security_rules(path: Path) -> SecurityRules:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return SecurityRules(
        forbidden_paths=_normalize_rule_values(raw.get("forbidden_paths", [])),
        forbidden_globs=_normalize_rule_values(raw.get("forbidden_globs", [])),
        forbidden_extensions=_normalize_rule_values(raw.get("forbidden_extensions", []), lower=True),
        forbidden_literal_markers=_normalize_rule_values(raw.get("forbidden_literal_markers", [])),
        forbidden_regex_markers=_normalize_rule_values(raw.get("forbidden_regex_markers", [])),
        ignored_paths=_normalize_rule_values(raw.get("ignored_paths", [])),
        marker_ignored_paths=_normalize_rule_values(raw.get("marker_ignored_paths", [])),
    )


def verify_security(*, repo_root: Path, rules_path: Path) -> SecurityReport:
    normalized_root = repo_root.resolve()
    normalized_rules = rules_path.resolve()
    rules = load_security_rules(normalized_rules)
    candidate_paths = collect_staged_paths(normalized_root)
    return scan_security_paths(
        repo_root=normalized_root,
        rules_path=normalized_rules,
        rules=rules,
        candidate_paths=candidate_paths,
    )


def scan_security_paths(
    *,
    repo_root: Path,
    rules_path: Path,
    rules: SecurityRules,
    candidate_paths: list[str],
) -> SecurityReport:
    skipped_paths = {path_text for path_text in candidate_paths if _is_ignored_path(path_text, rules)}
    try:
        skipped_paths.add(rules_path.relative_to(repo_root).as_posix())
    except ValueError:
        pass
    findings: list[SecurityFinding] = []
    findings.extend(_check_forbidden_paths(candidate_paths, rules))
    findings.extend(_check_forbidden_extensions(candidate_paths, rules))
    findings.extend(_check_python_source_risks(repo_root, candidate_paths, skipped_paths=skipped_paths))
    findings.extend(_check_config_hygiene(repo_root, candidate_paths, skipped_paths=skipped_paths))
    findings.extend(
        _check_forbidden_markers(
            repo_root,
            candidate_paths,
            rules,
            skipped_paths=skipped_paths,
        )
    )
    findings.sort(key=lambda finding: (finding.path, finding.kind, finding.line or 0, finding.matched_rule))
    return SecurityReport(
        repo_root=repo_root,
        rules_path=rules_path,
        files_scanned=len([path for path in candidate_paths if path not in skipped_paths]),
        findings=tuple(findings),
    )


def render_security_report(report: SecurityReport) -> str:
    if not report.findings:
        if report.files_scanned == 0:
            return (
                f"Security scan passed: no staged files to inspect under {report.repo_root} "
                f"using {report.rules_path}."
            )
        return (
            f"Security scan passed: scanned {report.files_scanned} staged file(s) under {report.repo_root} "
            f"using {report.rules_path}."
        )

    lines = [
        (
            f"Security scan failed: {len(report.findings)} finding(s) across "
            f"{report.files_scanned} scanned staged file(s)."
        )
    ]
    for finding in report.findings:
        location = finding.path
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(f"- [{finding.kind}] {location} | rule={finding.matched_rule} | {finding.message}")
    return "\n".join(lines)


def collect_staged_paths(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            cwd=repo_root,
            text=False,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("security scan requires a readable git index") from exc

    raw_paths = [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\x00") if item]
    normalized = sorted(_normalize_relative_path(path) for path in raw_paths if path)
    return normalized


def _normalize_rule_values(values: object, *, lower: bool = False) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise ValueError("security rule values must be lists")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("security rules must contain only strings")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("security rules must not contain empty strings")
        normalized.append(cleaned.lower() if lower else cleaned)
    return tuple(normalized)


def _normalize_relative_path(path_text: str) -> str:
    return PurePosixPath(path_text.strip()).as_posix()


def _is_ignored_path(path_text: str, rules: SecurityRules) -> bool:
    return any(_glob_matches(path_text, pattern) for pattern in rules.ignored_paths)


def _check_forbidden_paths(paths: list[str], rules: SecurityRules) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for path_text in paths:
        for forbidden in rules.forbidden_paths:
            if path_text == forbidden or path_text.startswith(f"{forbidden}/"):
                findings.append(
                    SecurityFinding(
                        kind="forbidden_path",
                        path=path_text,
                        message="path matches a forbidden security rule",
                        matched_rule=forbidden,
                    )
                )
        for pattern in rules.forbidden_globs:
            if _glob_matches(path_text, pattern):
                findings.append(
                    SecurityFinding(
                        kind="forbidden_path",
                        path=path_text,
                        message="path matches a forbidden security glob",
                        matched_rule=pattern,
                    )
                )
    return findings


def _check_forbidden_extensions(paths: list[str], rules: SecurityRules) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    forbidden_extensions = set(rules.forbidden_extensions)
    for path_text in paths:
        suffix = Path(path_text).suffix.lower()
        if suffix and suffix in forbidden_extensions:
            findings.append(
                SecurityFinding(
                    kind="forbidden_extension",
                    path=path_text,
                    message="file extension is not allowed in security-scoped commits",
                    matched_rule=suffix,
                )
            )
    return findings


def _check_forbidden_markers(
    repo_root: Path,
    paths: list[str],
    rules: SecurityRules,
    *,
    skipped_paths: set[str],
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    regex_patterns = tuple(re.compile(pattern) for pattern in rules.forbidden_regex_markers)
    for path_text in paths:
        if path_text in skipped_paths:
            continue
        if any(_glob_matches(path_text, pattern) for pattern in rules.marker_ignored_paths):
            continue
        text = _read_text_candidate(repo_root / path_text)
        if text is None:
            continue
        for literal in rules.forbidden_literal_markers:
            index = text.find(literal)
            if index == -1:
                continue
            findings.append(
                SecurityFinding(
                    kind="forbidden_marker",
                    path=path_text,
                    message="file contains a forbidden literal security marker",
                    matched_rule=literal,
                    line=_line_number_for_offset(text, index),
                )
            )
        for pattern in regex_patterns:
            match = pattern.search(text)
            if match is None:
                continue
            findings.append(
                SecurityFinding(
                    kind="forbidden_marker",
                    path=path_text,
                    message="file contains a forbidden regex security marker",
                    matched_rule=pattern.pattern,
                    line=_line_number_for_offset(text, match.start()),
                )
            )
    return findings


def _check_python_source_risks(
    repo_root: Path,
    paths: list[str],
    *,
    skipped_paths: set[str],
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for path_text in paths:
        if path_text in skipped_paths:
            continue
        if Path(path_text).suffix.lower() not in SOURCE_AST_EXTENSIONS:
            continue
        text = _read_text_candidate(repo_root / path_text)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=path_text)
        except SyntaxError:
            continue
        findings.extend(_check_python_ast_nodes(path_text, tree))
    return findings


def _check_config_hygiene(
    repo_root: Path,
    paths: list[str],
    *,
    skipped_paths: set[str],
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for path_text in paths:
        if path_text in skipped_paths:
            continue
        normalized_path = Path(path_text)
        if not _is_config_hygiene_candidate(normalized_path):
            continue
        text = _read_text_candidate(repo_root / path_text)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = CONFIG_SECRET_ASSIGNMENT_RE.match(line)
            if match is None:
                continue
            value = match.group("value").strip().strip("'\"")
            if _looks_like_config_placeholder(value):
                continue
            findings.append(
                SecurityFinding(
                    kind="config_hygiene",
                    path=path_text,
                    message="config file contains a secret-like assignment",
                    matched_rule=match.group("quoted_key") or match.group("plain_key") or "config-secret-assignment",
                    line=line_no,
                )
            )
    return findings


def _is_config_hygiene_candidate(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in CONFIG_HYGIENE_EXTENSIONS:
        return True
    return path.name.startswith(".env") or path.name.endswith(".env")


def _looks_like_config_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(token in lowered for token in CONFIG_SECRET_PLACEHOLDERS)


def _check_python_ast_nodes(path_text: str, tree: ast.AST) -> list[SecurityFinding]:
    import_aliases = _build_import_aliases(tree)
    findings: list[SecurityFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved_call = _resolve_call_name(node.func, import_aliases)
        if resolved_call in {"eval", "exec"}:
            findings.append(
                SecurityFinding(
                    kind="dangerous_code",
                    path=path_text,
                    message="call executes dynamically evaluated code",
                    matched_rule=resolved_call,
                    line=node.lineno,
                )
            )
            continue
        if resolved_call in {"os.system", "os.popen"}:
            findings.append(
                SecurityFinding(
                    kind="dangerous_code",
                    path=path_text,
                    message="call executes a shell command through os.*",
                    matched_rule=resolved_call,
                    line=node.lineno,
                )
            )
            continue
        if resolved_call in {
            "subprocess.run",
            "subprocess.call",
            "subprocess.Popen",
            "subprocess.check_call",
            "subprocess.check_output",
        } and _has_true_keyword(node, "shell"):
            findings.append(
                SecurityFinding(
                    kind="dangerous_code",
                    path=path_text,
                    message="subprocess call enables shell execution",
                    matched_rule=resolved_call,
                    line=node.lineno,
                )
            )
    return findings


def _build_import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _resolve_call_name(func: ast.expr, import_aliases: dict[str, str]) -> str:
    if isinstance(func, ast.Name):
        return import_aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        owner = _resolve_call_name(func.value, import_aliases)
        if owner == "call":
            return "call"
        return f"{owner}.{func.attr}"
    return "call"


def _has_true_keyword(node: ast.Call, keyword_name: str) -> bool:
    for keyword in node.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
            return True
    return False


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
