"""SQLite persistence for per-call transcripts (stdlib sqlite3)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def init_db(path: str | None = None) -> None:
    """Create DB file, parent dirs, and ``call_logs`` table if needed."""
    path = path or os.getenv("CALL_LOG_DB_PATH", "./data/call_logs.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_call_id TEXT,
                plivo_call_id TEXT,
                route TEXT,
                started_at TEXT,
                ended_at TEXT,
                duration_ms REAL,
                transcript_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_call_logs_session ON call_logs(session_call_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_call_logs_plivo ON call_logs(plivo_call_id)"
        )
        conn.commit()


def insert_call_log(
    *,
    session_call_id: str | None,
    plivo_call_id: str | None,
    route: str,
    started_at: str,
    ended_at: str,
    duration_ms: float,
    transcript: list[dict[str, Any]],
) -> None:
    path = os.getenv("CALL_LOG_DB_PATH", "./data/call_logs.db")
    init_db(path)
    payload = json.dumps(transcript, ensure_ascii=False)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO call_logs (
                session_call_id, plivo_call_id, route,
                started_at, ended_at, duration_ms, transcript_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_call_id,
                plivo_call_id,
                route,
                started_at,
                ended_at,
                duration_ms,
                payload,
            ),
        )
        conn.commit()
