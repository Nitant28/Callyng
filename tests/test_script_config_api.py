"""Integration tests for /internal/script-configs admin API."""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from dotenv import load_dotenv

load_dotenv(override=True)

from db import postgres as pg_db



@pytest.fixture
def client(test_client):
    yield test_client


def _admin_headers() -> dict[str, str]:
    key = (os.getenv("ADMIN_API_KEY") or "").strip()
    if not key:
        pytest.skip("ADMIN_API_KEY not set")
    return {"X-Admin-Key": key}


async def _test_pool():
    dsn = (os.getenv("DATABASE_URL") or "").strip()
    if not dsn:
        pytest.skip("DATABASE_URL not set")
    try:
        return await asyncpg.create_pool(dsn, min_size=1, max_size=3, command_timeout=30)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


@pytest.mark.asyncio
async def test_get_template_sts(client):
    res = await client.get(
        "/internal/script-configs/template",
        params={"route": "sts"},
        headers=_admin_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["route"] == "sts"
    assert "extraction_schema" in body["template"]
    assert body["template"]["gemini_model"]


@pytest.mark.asyncio
async def test_create_patch_revisions_rollback(client):
    if True:
        pool = await _test_pool()
        client_id, _ = await pg_db.create_client(
            pool,
            f"SC API {uuid.uuid4().hex[:8]}",
            "sc@test.com",
            "other",
        )
        try:
            res = await client.get(
                "/internal/script-configs/template",
                params={"route": "sts"},
                headers=_admin_headers(),
            )
            tpl = res.json()["template"]

            create_payload = {
                "client_id": str(client_id),
                **tpl,
                "script_id": f"sc_{uuid.uuid4().hex[:8]}",
            }
            res = await client.post(
                "/internal/script-configs",
                json=create_payload,
                headers=_admin_headers(),
            )
            assert res.status_code == 200, res.text
            sc = res.json()["script_config"]
            assert sc["version"] == 1
            sc_id = sc["id"]

            res = await client.patch(
                f"/internal/script-configs/{sc_id}",
                params={"client_id": str(client_id)},
                json={"gemini_voice": "Puck"},
                headers=_admin_headers(),
            )
            assert res.status_code == 200, res.text
            assert res.json()["script_config"]["version"] == 2
            assert res.json()["script_config"]["gemini_voice"] == "Puck"

            res = await client.get(
                f"/internal/script-configs/{sc_id}/revisions",
                params={"client_id": str(client_id)},
                headers=_admin_headers(),
            )
            assert res.status_code == 200
            versions = [r["version"] for r in res.json()["revisions"]]
            assert 1 in versions and 2 in versions

            res = await client.post(
                f"/internal/script-configs/{sc_id}/rollback",
                params={"client_id": str(client_id)},
                json={"version": 1},
                headers=_admin_headers(),
            )
            assert res.status_code == 200, res.text
            rolled = res.json()["script_config"]
            assert rolled["version"] == 3
            assert rolled["gemini_voice"] == tpl.get("gemini_voice", "Aoede")

            res = await client.get(
                f"/internal/script-configs/{sc_id}/revisions",
                params={"client_id": str(client_id)},
                headers=_admin_headers(),
            )
            assert 3 in [r["version"] for r in res.json()["revisions"]]
        finally:
            await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()


@pytest.mark.asyncio
async def test_create_invalid_outcome_mapping(client):
    if True:
        pool = await _test_pool()
        client_id, _ = await pg_db.create_client(
            pool,
            f"SC Bad {uuid.uuid4().hex[:8]}",
            "bad@test.com",
            "other",
        )
        try:
            res = await client.get(
                "/internal/script-configs/template",
                params={"route": "sts"},
                headers=_admin_headers(),
            )
            tpl = res.json()["template"]
            tpl["outcome_retry"] = ["Busy"]
            tpl["script_id"] = f"bad_{uuid.uuid4().hex[:8]}"
            res = await client.post(
                "/internal/script-configs",
                json={"client_id": str(client_id), **tpl},
                headers=_admin_headers(),
            )
            assert res.status_code == 422
        finally:
            await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()


@pytest.mark.asyncio
async def test_test_endpoint_mocked(client):
    if True:
        pool = await _test_pool()
        client_id, _ = await pg_db.create_client(
            pool,
            f"SC Test {uuid.uuid4().hex[:8]}",
            "test@test.com",
            "other",
        )
        try:
            res = await client.get(
                "/internal/script-configs/template",
                params={"route": "sts"},
                headers=_admin_headers(),
            )
            tpl = res.json()["template"]
            tpl["script_id"] = f"tst_{uuid.uuid4().hex[:8]}"
            res2 = await client.post(
                "/internal/script-configs",
                json={"client_id": str(client_id), **tpl},
                headers=_admin_headers(),
            )
            sc = res2.json()["script_config"]
            sc_id = sc["id"]

            with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
                with patch(
                    "api.routes.internal_script_configs.extract_post_call",
                    new_callable=AsyncMock,
                ) as mock_extract:
                    mock_extract.return_value = (
                        {"intent_status": "Interested"},
                        None,
                        "llama-3.3-70b-versatile",
                    )
                    res = await client.post(
                        f"/internal/script-configs/{sc_id}/test",
                        params={"client_id": str(client_id)},
                        json={
                            "transcript": [
                                {"role": "user", "content": "yes interested"}
                            ]
                        },
                        headers=_admin_headers(),
                    )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["parsed"]["intent_status"] == "Interested"
            assert body["normalized"] is not None
        finally:
            await pool.execute("DELETE FROM clients WHERE id = $1", client_id)
            await pool.close()
