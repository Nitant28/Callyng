"""Unit tests for multi-select lead filter helpers (OR within / AND across)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from db import postgres as pg_db


def test_normalize_filter_list_single_and_csv():
    assert pg_db._normalize_filter_list(None) == []
    assert pg_db._normalize_filter_list("") == []
    assert pg_db._normalize_filter_list("pending") == ["pending"]
    assert pg_db._normalize_filter_list("pending,calling") == ["pending", "calling"]
    assert pg_db._normalize_filter_list("pending, pending,calling") == ["pending", "calling"]
    assert pg_db._normalize_filter_list(["pending", "calling"]) == ["pending", "calling"]


def test_attempts_and_turns_or_clauses():
    args: list = []
    clause, args, idx = pg_db._attempts_or_clause(["1", "4+"], args, 3)
    assert "l.attempts = $3" in clause
    assert "l.attempts >= 4" in clause
    assert " OR " in clause
    assert args == [1]
    assert idx == 4

    args2: list = []
    turns_clause, args2, idx2 = pg_db._turns_or_clause(
        ["0", "1-3", "9+", "2"],
        "COALESCE(lc.turn_count, 0)",
        args2,
        5,
    )
    assert "= 0" in turns_clause
    assert "BETWEEN 1 AND 3" in turns_clause
    assert ">= 9" in turns_clause
    assert "= $5" in turns_clause
    assert args2 == [2]
    assert idx2 == 6


@pytest.mark.asyncio
async def test_list_campaign_leads_multi_filters_sql():
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=0)
    pool.fetch = AsyncMock(return_value=[])

    await pg_db.list_campaign_leads(
        pool,
        uuid4(),
        uuid4(),
        limit=25,
        offset=0,
        status="pending,calling",
        outcome="Interested,Callback_Requested",
        turns="1-3,9+",
        attempts="1,4+",
    )

    list_sql = pool.fetch.await_args.args[0]
    count_sql = pool.fetchval.await_args.args[0]
    list_args = pool.fetch.await_args.args[1:]

    assert "l.status = ANY($3::text[])" in list_sql
    assert "l.outcome = ANY(" in list_sql
    assert "l.attempts = $" in list_sql
    assert "l.attempts >= 4" in list_sql
    assert "BETWEEN 1 AND 3" in list_sql
    assert ">= 9" in list_sql
    assert " AND " in list_sql
    assert list_args[2] == ["pending", "calling"]
    assert "Interested" in list_args[3]
    assert "LEFT JOIN LATERAL" in count_sql
