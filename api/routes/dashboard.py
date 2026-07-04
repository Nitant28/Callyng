"""Unified dashboard analytics endpoint for clients.

Returns KPIs, simple hourly charts, and recent activity aggregated from
campaigns and call_logs. This keeps business logic on the backend so the
frontend can render without recomputing metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.auth import get_client_from_token, get_pool, client_id_uuid
from db import postgres as pg_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


@router.get("/analytics")
async def get_dashboard_analytics(
    period_days: int = Query(7, ge=1, le=90),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Return a single analytics payload for the dashboard.

    Response shape (partial):
    {
      "summary": { ... },
      "charts": { "hourly_calls": [...], "hourly_interested": [...] },
      "recent_activity": [...],
      "campaigns": [...],
      "generated_at": "...",
    }
    """
    cid = client_id_uuid(client)

    # Fetch campaigns (single-shot)
    campaigns = await pg_db.list_campaigns(pool, cid)

    # Per-campaign interested counts (fast aggregate)
    interested_map = await pg_db.get_campaigns_interested_counts(pool, cid)

    # Recent calls (limit small for activity)
    recent_calls, total_calls = await pg_db.list_call_logs(pool, cid, limit=50, offset=0)

    # KPI calculations (use campaign aggregate fields when available)
    total_campaigns = len(campaigns or [])
    running_campaigns = sum(1 for c in (campaigns or []) if (c.get("status") or "").lower() == "running")
    interested_leads = sum(int(interested_map.get(str(c.get("id")), 0)) for c in (campaigns or []))
    # answered_leads prefer campaign field
    answered_leads = sum(int(c.get("answered_leads" or 0) or 0) for c in (campaigns or []))

    # credits: prefer campaign budget_used_credits aggregate, fallback to sum of call charges
    credits_used = 0
    for c in (campaigns or []):
        credits_used += float(c.get("budget_used_credits") or c.get("credits_used") or 0)

    # client balance
    remaining_credits = float(client.get("balance_credits") or 0)
    total_credits = None
    if remaining_credits is not None:
        total_credits = remaining_credits + credits_used

    # live calls
    live_calls = sum(1 for cl in (recent_calls or []) if cl.get("in_progress") is True)

    # Charts: hourly aggregates for the requested window
    window_start = datetime.utcnow() - timedelta(days=period_days)
    hourly_calls_rows = await pool.fetch(
        """
        SELECT date_trunc('hour', started_at) AS bucket, COUNT(*)::int AS calls
        FROM call_logs
        WHERE client_id = $1
          AND started_at >= $2
          AND (call_data->>'is_test_call' IS NULL OR call_data->>'is_test_call' != 'true')
        GROUP BY 1
        ORDER BY 1
        """,
        cid,
        window_start,
    )

    hourly_interested_rows = await pool.fetch(
        """
        SELECT date_trunc('hour', started_at) AS bucket, COUNT(*)::int AS interested
        FROM call_logs
        WHERE client_id = $1
          AND started_at >= $2
          AND outcome = 'Interested'
          AND (call_data->>'is_test_call' IS NULL OR call_data->>'is_test_call' != 'true')
        GROUP BY 1
        ORDER BY 1
        """,
        cid,
        window_start,
    )

    hourly_calls = [{"bucket": _iso(r["bucket"]), "calls": int(r["calls"])} for r in hourly_calls_rows]
    hourly_interested = [{"bucket": _iso(r["bucket"]), "interested": int(r["interested"])} for r in hourly_interested_rows]

    # Recent activity: map recent calls + simple campaign status events
    activity = []
    for cl in recent_calls:
        activity.append(
            {
                "id": cl.get("id") or cl.get("session_call_id"),
                "type": "call",
                "campaign_id": cl.get("campaign_id"),
                "campaign_name": cl.get("campaign_name") or cl.get("campaign") or None,
                "lead_name": cl.get("name") or cl.get("lead_name") or None,
                "outcome": cl.get("outcome") or cl.get("status") or None,
                "timestamp": _iso(cl.get("started_at") or cl.get("created_at") or cl.get("ended_at")),
                "credits_charged": float(cl.get("credits_charged") or cl.get("credits_used") or 0),
            }
        )

    # Campaign events (simple recent status marker)
    for c in (campaigns or [])[:20]:
        ts = c.get("updated_at") or c.get("created_at")
        if not ts:
            continue
        activity.append(
            {
                "id": f"campaign-{c.get('id')}-{c.get('status')}",
                "type": "campaign",
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name") or c.get("title") or None,
                "outcome": c.get("status"),
                "timestamp": _iso(ts),
            }
        )

    # Sort activity by timestamp desc and limit
    activity = sorted(activity, key=lambda x: x.get("timestamp") or "", reverse=True)[:50]

    payload = {
        "summary": {
            "totalCampaigns": total_campaigns,
            "runningCampaigns": running_campaigns,
            "interestedLeads": int(interested_leads),
            "answeredLeads": int(answered_leads or 0),
            "liveCalls": int(live_calls),
            "totalCalls": int(total_calls or 0),
            "creditsUsed": float(credits_used),
            "remainingCredits": float(remaining_credits),
            "totalCredits": float(total_credits) if total_credits is not None else None,
        },
        "charts": {
            "hourly_calls": hourly_calls,
            "hourly_interested": hourly_interested,
        },
        "recent_activity": activity,
        "campaigns": campaigns,
        "generated_at": datetime.utcnow().isoformat(),
    }

    return payload
