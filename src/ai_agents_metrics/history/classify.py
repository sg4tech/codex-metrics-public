"""Structural classifier for agent session kinds.

Implements H-040 MVP: a deterministic, filename-based classifier that distinguishes
main agent sessions from subagent spawns. See docs/findings/F-001 for motivation —
on a 6-month Claude Code history, 100% of naive "retry count" was subagent aliasing,
not user retries. This module produces `derived_session_kinds` which downstream
aggregates (e.g. `derived_goals.main_attempt_count`) use to avoid that confound.

The classifier is intentionally minimal:
- No LLM, no payload heuristics.
- Filename-only rules, cross-verified against F-001's 100% deterministic match.
- Versioned output so reclassification can be skipped if rules have not changed.

Layer: classified derived (Layer 3) — see oss/docs/warehouse-layering.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_agents_metrics.history.derive_schema import (
    _clear_derived_practice_events,
    _clear_derived_session_kinds,
    _ensure_schema,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

SESSION_KIND_MAIN = "main"
SESSION_KIND_SUBAGENT = "subagent"
SESSION_KIND_UNKNOWN = "unknown"

# Version derived from the config of rules below.
# Bump by changing the config string when rules change — classify output is
# idempotent per (classifier_version, input set).
_CLASSIFIER_CONFIG_V1 = "v1:filename:agent-prefix|subagents-dir"
CLASSIFIER_VERSION = "v1-" + hashlib.sha256(_CLASSIFIER_CONFIG_V1.encode("utf-8")).hexdigest()[:8]

# Practice-event classifier — see docs/findings/F-003. Catalog derived from a full
# 6-month Claude Code warehouse (oss/docs/findings/F-003-*). Unknown names fall
# through to PRACTICE_FAMILY_OTHER, so adding a new skill does not drop rows.
PRACTICE_SOURCE_AGENT = "agent"
PRACTICE_SOURCE_SKILL = "skill"

PRACTICE_FAMILY_CODE_REVIEW = "code_review"
PRACTICE_FAMILY_DISCOVERY = "discovery"
PRACTICE_FAMILY_PLANNING = "planning"
PRACTICE_FAMILY_PR_REVIEW = "pr_review"
PRACTICE_FAMILY_COMMIT_WORKFLOW = "commit_workflow"
PRACTICE_FAMILY_TEST_ANALYSIS = "test_analysis"
PRACTICE_FAMILY_REVIEW_ANALYSIS = "review_analysis"
PRACTICE_FAMILY_METRICS_REVIEW = "metrics_review"
PRACTICE_FAMILY_OTHER = "other"

_PRACTICE_FAMILY_BY_AGENT = {
    "Explore": PRACTICE_FAMILY_DISCOVERY,
    "general-purpose": PRACTICE_FAMILY_DISCOVERY,
    "claude-code-guide": PRACTICE_FAMILY_DISCOVERY,
    "Plan": PRACTICE_FAMILY_PLANNING,
    "pr-review-toolkit:code-reviewer": PRACTICE_FAMILY_CODE_REVIEW,
    "pr-review-toolkit:pr-test-analyzer": PRACTICE_FAMILY_TEST_ANALYSIS,
    "pr-review-toolkit:comment-analyzer": PRACTICE_FAMILY_REVIEW_ANALYSIS,
    "pr-review-toolkit:silent-failure-hunter": PRACTICE_FAMILY_REVIEW_ANALYSIS,
    "pr-review-toolkit:type-design-analyzer": PRACTICE_FAMILY_REVIEW_ANALYSIS,
}

_PRACTICE_FAMILY_BY_SKILL = {
    "code-review:code-review": PRACTICE_FAMILY_CODE_REVIEW,
    "code-review": PRACTICE_FAMILY_CODE_REVIEW,
    "pr-review-toolkit:review-pr": PRACTICE_FAMILY_PR_REVIEW,
    "review-pr": PRACTICE_FAMILY_PR_REVIEW,
    "commit-commands:commit": PRACTICE_FAMILY_COMMIT_WORKFLOW,
    "commit-commands:commit-push-pr": PRACTICE_FAMILY_COMMIT_WORKFLOW,
    "commit": PRACTICE_FAMILY_COMMIT_WORKFLOW,
    "product-management:metrics-review": PRACTICE_FAMILY_METRICS_REVIEW,
}

_PRACTICE_CATALOG_CONFIG_V1 = (
    "v1:agent+skill:"
    + "|".join(f"{k}={v}" for k, v in sorted(_PRACTICE_FAMILY_BY_AGENT.items()))
    + "||"
    + "|".join(f"{k}={v}" for k, v in sorted(_PRACTICE_FAMILY_BY_SKILL.items()))
)
PRACTICE_EVENT_CLASSIFIER_VERSION = (
    "v1-" + hashlib.sha256(_PRACTICE_CATALOG_CONFIG_V1.encode("utf-8")).hexdigest()[:8]
)


def _classify_practice_family(source_kind: str, practice_name: str) -> str:
    """Map (source_kind, practice_name) to a practice family label.

    Unknown names fall through to PRACTICE_FAMILY_OTHER so the extractor stays
    lossless — adding a new skill to the catalog is purely additive.
    """
    if source_kind == PRACTICE_SOURCE_AGENT:
        return _PRACTICE_FAMILY_BY_AGENT.get(practice_name, PRACTICE_FAMILY_OTHER)
    if source_kind == PRACTICE_SOURCE_SKILL:
        return _PRACTICE_FAMILY_BY_SKILL.get(practice_name, PRACTICE_FAMILY_OTHER)
    return PRACTICE_FAMILY_OTHER


def _classify_session_kind(session_path: str) -> str:
    """Classify a session file by its filename.

    Rules (deterministic, 100% match on F-001 dataset):
      - Basename starting with 'agent-'            -> subagent
      - Path containing '/subagents/'              -> subagent
      - Any other '.jsonl' under a Claude or Codex session directory -> main

    Returns SESSION_KIND_UNKNOWN only if the path has no recognizable structure.
    """
    if not session_path:
        return SESSION_KIND_UNKNOWN
    base = Path(session_path).name
    if base.startswith("agent-"):
        return SESSION_KIND_SUBAGENT
    normalized = session_path.replace("\\", "/")
    if "/subagents/" in normalized:
        return SESSION_KIND_SUBAGENT
    if base.endswith(".jsonl"):
        return SESSION_KIND_MAIN
    return SESSION_KIND_UNKNOWN


@dataclass(frozen=True)
class ClassifySummary:
    warehouse_path: Path
    classifier_version: str
    sessions_total: int
    main_sessions: int
    subagent_sessions: int
    unknown_sessions: int
    practice_event_classifier_version: str = ""
    practice_events_total: int = 0
    practice_events_by_family: tuple[tuple[str, int], ...] = ()


def _iter_tool_use_blocks(node: object) -> Iterator[dict[str, Any]]:
    """Walk a JSON-decoded value and yield every dict with type == 'tool_use'."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use":
            yield node
        for value in node.values():
            yield from _iter_tool_use_blocks(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_tool_use_blocks(item)


@dataclass(frozen=True)
class PracticeSourceRow:
    """Source-row identity for a raw_session_events tool_use payload."""

    event_id: str
    session_path: str
    thread_id: str | None
    source_path: str
    event_index: int
    timestamp: str | None
    raw_json: str


def _extract_practice_rows(
    source_row: PracticeSourceRow,
    *,
    classifier_version: str,
    classified_at: str,
) -> list[tuple[Any, ...]]:
    """Parse one raw_session_events row and return zero or more practice rows.

    Each row is a tuple aligned with the INSERT statement columns in
    _insert_practice_row. Unparseable payloads yield no rows (not an error —
    tool_use blocks may legitimately be absent).
    """
    try:
        payload = json.loads(source_row.raw_json)
    except (TypeError, ValueError):
        return []
    rows: list[tuple[Any, ...]] = []
    for tool_use_ordinal, block in enumerate(_iter_tool_use_blocks(payload)):
        name = block.get("name")
        raw_input = block.get("input")
        inp: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
        if name == "Agent":
            source_kind = PRACTICE_SOURCE_AGENT
            practice_name = str(inp.get("subagent_type") or "<missing>")
        elif name == "Skill":
            source_kind = PRACTICE_SOURCE_SKILL
            practice_name = str(inp.get("skill") or "<missing>")
        else:
            continue
        family = _classify_practice_family(source_kind, practice_name)
        tool_use_id = block.get("id")
        # Deterministic PK: (event_id, tool_use_ordinal) — stable across reruns.
        practice_event_id = f"{source_row.event_id}:{tool_use_ordinal}"
        raw_row = json.dumps(
            {
                "practice_event_id": practice_event_id,
                "session_path": source_row.session_path,
                "thread_id": source_row.thread_id,
                "source_path": source_row.source_path,
                "event_index": source_row.event_index,
                "timestamp": source_row.timestamp,
                "tool_use_id": tool_use_id,
                "source_kind": source_kind,
                "practice_name": practice_name,
                "practice_family": family,
                "classifier_version": classifier_version,
                "classified_at": classified_at,
            },
            sort_keys=True,
        )
        rows.append(
            (
                practice_event_id,
                source_row.session_path,
                source_row.thread_id,
                source_row.source_path,
                source_row.event_index,
                source_row.timestamp,
                tool_use_id,
                source_kind,
                practice_name,
                family,
                classifier_version,
                classified_at,
                raw_row,
            )
        )
    return rows


def _insert_practice_row(conn: sqlite3.Connection, row: tuple[Any, ...]) -> None:
    conn.execute(
        """
        INSERT INTO derived_practice_events (
            practice_event_id, session_path, thread_id, source_path,
            event_index, timestamp, tool_use_id, source_kind,
            practice_name, practice_family,
            classifier_version, classified_at, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )


def _classify_practice_events(
    conn: sqlite3.Connection,
    *,
    classified_at: str,
) -> tuple[int, dict[str, int]]:
    """Scan raw_session_events, write derived_practice_events, return counts."""
    _clear_derived_practice_events(conn)
    total = 0
    by_family: dict[str, int] = {}
    cur = conn.execute(
        """
        SELECT event_id, session_path, thread_id, source_path,
               event_index, timestamp, raw_json
        FROM raw_session_events
        WHERE raw_json LIKE '%"type":"tool_use"%'
           OR raw_json LIKE '%"type": "tool_use"%'
        ORDER BY session_path, event_index
        """
    )
    for row in cur:
        practice_rows = _extract_practice_rows(
            PracticeSourceRow(
                event_id=row["event_id"],
                session_path=row["session_path"],
                thread_id=row["thread_id"],
                source_path=row["source_path"],
                event_index=row["event_index"],
                timestamp=row["timestamp"],
                raw_json=row["raw_json"],
            ),
            classifier_version=PRACTICE_EVENT_CLASSIFIER_VERSION,
            classified_at=classified_at,
        )
        for practice_row in practice_rows:
            _insert_practice_row(conn, practice_row)
            total += 1
            family = practice_row[9]
            by_family[family] = by_family.get(family, 0) + 1
    return total, by_family


def _fetch_normalized_session_refs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT session_path, thread_id, source_path
        FROM normalized_sessions
        ORDER BY session_path
        """
    )
    return cur.fetchall()


def classify_codex_history(*, warehouse_path: Path) -> ClassifySummary:
    """Read normalized sessions from the warehouse and write derived_session_kinds.

    Overwrites any prior derived_session_kinds rows — the classifier is
    deterministic and cheap, so a full refresh is simpler than incremental update.
    """
    if not warehouse_path.exists():
        raise ValueError(
            f"Warehouse does not exist: {warehouse_path}. "
            "Run 'ai-agents-metrics history-update' first."
        )

    main_count = 0
    subagent_count = 0
    unknown_count = 0

    classified_at = datetime.now(UTC).isoformat()

    with sqlite3.connect(warehouse_path) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        try:
            session_refs = _fetch_normalized_session_refs(conn)
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "Warehouse does not contain normalized agent history; run history-normalize first"
            ) from exc

        _clear_derived_session_kinds(conn)

        for row in session_refs:
            session_path = row["session_path"]
            thread_id = row["thread_id"]
            source_path = row["source_path"]
            kind = _classify_session_kind(session_path)
            if kind == SESSION_KIND_MAIN:
                main_count += 1
            elif kind == SESSION_KIND_SUBAGENT:
                subagent_count += 1
            else:
                unknown_count += 1
            raw_json = json.dumps(
                {
                    "session_path": session_path,
                    "thread_id": thread_id,
                    "source_path": source_path,
                    "kind": kind,
                    "classifier_version": CLASSIFIER_VERSION,
                    "classified_at": classified_at,
                },
                sort_keys=True,
            )
            conn.execute(
                """
                INSERT INTO derived_session_kinds (
                    session_path, thread_id, source_path, kind,
                    classifier_version, classified_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_path, thread_id, source_path, kind, CLASSIFIER_VERSION, classified_at, raw_json),
            )

        practice_total, practice_by_family = _classify_practice_events(
            conn, classified_at=classified_at
        )

        conn.commit()

    return ClassifySummary(
        warehouse_path=warehouse_path,
        classifier_version=CLASSIFIER_VERSION,
        sessions_total=main_count + subagent_count + unknown_count,
        main_sessions=main_count,
        subagent_sessions=subagent_count,
        unknown_sessions=unknown_count,
        practice_event_classifier_version=PRACTICE_EVENT_CLASSIFIER_VERSION,
        practice_events_total=practice_total,
        practice_events_by_family=tuple(sorted(practice_by_family.items())),
    )


def render_classify_summary_json(summary: ClassifySummary) -> str:
    return json.dumps(
        {
            "warehouse_path": str(summary.warehouse_path),
            "classifier_version": summary.classifier_version,
            "sessions_total": summary.sessions_total,
            "main_sessions": summary.main_sessions,
            "subagent_sessions": summary.subagent_sessions,
            "unknown_sessions": summary.unknown_sessions,
            "practice_event_classifier_version": summary.practice_event_classifier_version,
            "practice_events_total": summary.practice_events_total,
            "practice_events_by_family": dict(summary.practice_events_by_family),
        }
    )
