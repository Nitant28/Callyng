"""SQLite persistence for per-call transcripts (stdlib sqlite3)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from loguru import logger


def _db_path(path: str | None = None) -> str:
    return path or os.getenv("CALL_LOG_DB_PATH", "./data/call_logs.db")


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(call_logs)")
    existing = {row[1] for row in cur.fetchall()}
    alters: list[str] = []
    if "usage_prompt_tokens" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN usage_prompt_tokens INTEGER DEFAULT 0")
    if "usage_completion_tokens" not in existing:
        alters.append(
            "ALTER TABLE call_logs ADD COLUMN usage_completion_tokens INTEGER DEFAULT 0"
        )
    if "usage_total_tokens" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN usage_total_tokens INTEGER DEFAULT 0")
    if "usage_tts_characters" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN usage_tts_characters INTEGER DEFAULT 0")
    if "usage_metrics_json" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN usage_metrics_json TEXT")
    if "extraction_json" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN extraction_json TEXT")
    if "extraction_error" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN extraction_error TEXT")
    if "extraction_model" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN extraction_model TEXT")
    if "cost_inr" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN cost_inr REAL")
    if "recording_path" not in existing:
        alters.append("ALTER TABLE call_logs ADD COLUMN recording_path TEXT")
    for sql in alters:
        conn.execute(sql)


def init_db(path: str | None = None) -> None:
    """Create DB file, parent dirs, and ``call_logs`` table if needed."""
    path = _db_path(path)
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
        _ensure_columns(conn)
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
    usage_prompt_tokens: int = 0,
    usage_completion_tokens: int = 0,
    usage_total_tokens: int = 0,
    usage_tts_characters: int = 0,
    usage_metrics_json: str | None = None,
    cost_inr: float | None = None,
) -> int:
    """Insert one row; returns ``lastrowid`` for follow-up extraction updates."""
    path = _db_path()
    init_db(path)
    payload = json.dumps(transcript, ensure_ascii=False)
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO call_logs (
                session_call_id, plivo_call_id, route,
                started_at, ended_at, duration_ms, transcript_json,
                usage_prompt_tokens, usage_completion_tokens, usage_total_tokens,
                usage_tts_characters, usage_metrics_json, cost_inr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_call_id,
                plivo_call_id,
                route,
                started_at,
                ended_at,
                duration_ms,
                payload,
                usage_prompt_tokens,
                usage_completion_tokens,
                usage_total_tokens,
                usage_tts_characters,
                usage_metrics_json,
                cost_inr,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_call_log_extraction(
    row_id: int,
    *,
    extraction_json: str | None,
    extraction_error: str | None,
    extraction_model: str | None,
    path: str | None = None,
) -> None:
    if row_id <= 0:
        logger.warning(
            "update_call_log_extraction skipped: invalid row_id={}", row_id
        )
        return
    path = _db_path(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE call_logs
            SET extraction_json = ?, extraction_error = ?, extraction_model = ?
            WHERE id = ?
            """,
            (extraction_json, extraction_error, extraction_model, row_id),
        )
        conn.commit()


def get_row_id_by_session(session_call_id: str, path: str | None = None) -> int | None:
    """Look up the most recent SQLite call_logs row id for a session."""
    if not session_call_id:
        return None
    path = _db_path(path)
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            """
            SELECT id FROM call_logs
            WHERE session_call_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_call_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None
