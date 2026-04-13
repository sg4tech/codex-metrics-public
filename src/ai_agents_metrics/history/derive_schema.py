from __future__ import annotations

import sqlite3


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_goals (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            cwd TEXT,
            model_provider TEXT,
            model TEXT,
            title TEXT,
            archived INTEGER,
            session_count INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            timeline_event_count INTEGER NOT NULL,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_attempts (
            attempt_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            session_timestamp TEXT,
            cwd TEXT,
            source TEXT,
            model_provider TEXT,
            cli_version TEXT,
            originator TEXT,
            event_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            first_event_at TEXT,
            last_event_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_timeline_events (
            timeline_event_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT,
            attempt_index INTEGER,
            event_type TEXT NOT NULL,
            event_rank INTEGER NOT NULL,
            event_order INTEGER NOT NULL,
            timestamp TEXT,
            summary TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_message_facts (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER,
            event_index INTEGER NOT NULL,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            message_timestamp TEXT,
            message_date TEXT,
            text TEXT NOT NULL,
            model TEXT,
            usage_event_id TEXT,
            usage_event_index INTEGER,
            usage_timestamp TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            total_tokens INTEGER,
            raw_json TEXT NOT NULL
        )
        """
    )
    existing_message_fact_columns = {row[1] for row in conn.execute("PRAGMA table_info(derived_message_facts)").fetchall()}
    if "model" not in existing_message_fact_columns:
        conn.execute("ALTER TABLE derived_message_facts ADD COLUMN model TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_retry_chains (
            thread_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_count INTEGER NOT NULL,
            has_retry_pressure INTEGER NOT NULL,
            first_session_path TEXT,
            last_session_path TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_session_usage (
            session_usage_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            session_path TEXT NOT NULL,
            attempt_index INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            input_tokens INTEGER,
            cache_creation_input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            total_tokens INTEGER,
            first_usage_at TEXT,
            last_usage_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derived_projects (
            project_cwd TEXT PRIMARY KEY,
            parent_project_cwd TEXT,
            thread_count INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL,
            retry_thread_count INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            usage_event_count INTEGER NOT NULL,
            log_count INTEGER NOT NULL,
            timeline_event_count INTEGER NOT NULL,
            input_tokens INTEGER,
            cache_creation_input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT,
            raw_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_goals_cwd ON derived_goals(cwd)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_attempts_thread_id ON derived_attempts(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_timeline_thread_id ON derived_timeline_events(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_thread_id ON derived_message_facts(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_session_path ON derived_message_facts(session_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_message_date ON derived_message_facts(message_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_message_facts_model ON derived_message_facts(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_retry_chains_thread_id ON derived_retry_chains(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_session_usage_thread_id ON derived_session_usage(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_derived_projects_cwd ON derived_projects(project_cwd)")
    for table in ("derived_session_usage", "derived_projects"):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "cache_creation_input_tokens" not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN cache_creation_input_tokens INTEGER")
    existing_projects = {row[1] for row in conn.execute("PRAGMA table_info(derived_projects)").fetchall()}
    if "parent_project_cwd" not in existing_projects:
        conn.execute("ALTER TABLE derived_projects ADD COLUMN parent_project_cwd TEXT")


def _clear_derived_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM derived_goals")
    conn.execute("DELETE FROM derived_attempts")
    conn.execute("DELETE FROM derived_timeline_events")
    conn.execute("DELETE FROM derived_message_facts")
    conn.execute("DELETE FROM derived_retry_chains")
    conn.execute("DELETE FROM derived_session_usage")
    conn.execute("DELETE FROM derived_projects")
