#!/usr/bin/env python3
"""Print recent rows from SQLite call_logs (used by `just sqlite-calls`)."""

from __future__ import annotations

import os
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv(override=True)


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    db = os.getenv("CALL_LOG_DB_PATH", "./data/call_logs.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT session_call_id, route, duration_ms, extraction_json
        FROM call_logs
        ORDER BY rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    for r in rows:
        print(dict(r))
    conn.close()


if __name__ == "__main__":
    main()
