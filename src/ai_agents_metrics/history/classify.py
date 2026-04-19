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
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_agents_metrics.history.derive_schema import (
    _clear_derived_session_kinds,
    _ensure_schema,
)

SESSION_KIND_MAIN = "main"
SESSION_KIND_SUBAGENT = "subagent"
SESSION_KIND_UNKNOWN = "unknown"

# Version derived from the config of rules below.
# Bump by changing the config string when rules change — classify output is
# idempotent per (classifier_version, input set).
_CLASSIFIER_CONFIG_V1 = "v1:filename:agent-prefix|subagents-dir"
CLASSIFIER_VERSION = "v1-" + hashlib.sha256(_CLASSIFIER_CONFIG_V1.encode("utf-8")).hexdigest()[:8]


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
    base = os.path.basename(session_path)
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

    classified_at = datetime.now(timezone.utc).isoformat()

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

        conn.commit()

    return ClassifySummary(
        warehouse_path=warehouse_path,
        classifier_version=CLASSIFIER_VERSION,
        sessions_total=main_count + subagent_count + unknown_count,
        main_sessions=main_count,
        subagent_sessions=subagent_count,
        unknown_sessions=unknown_count,
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
        }
    )
