"""Unified dashboard analytics endpoint for clients.

Returns KPIs, chart series, and recent activity aggregated from
campaigns and call_logs. Business logic stays on the backend so the
frontend renders without recomputing metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.auth import client_id_uuid, get_client_from_token, get_pool
from db import postgres as pg_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

DAY_MS = 24 * 60 * 60 * 1000


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _resolve_period_window(
    period: str,
    custom_start: str | None,
    custom_end: str | None,
) -> tuple[datetime, datetime, str]:
    """Return (start, end, bucket_unit) where bucket_unit is 'hour' or 'day'."""
    now = datetime.now(UTC)

    if period == "today":
        return _start_of_day(now), now, "hour"

    if period == "yesterday":
        start = _start_of_day(now) - timedelta(days=1)
        return start, start + timedelta(days=1), "hour"

    if period == "custom" and custom_start and custom_end:
        start = _start_of_day(datetime.fromisoformat(custom_start.replace("Z", "+00:00")))
        end_raw = datetime.fromisoformat(custom_end.replace("Z", "+00:00"))
        end = end_raw.replace(hour=23, minute=59, second=59, microsecond=999999)
        duration_ms = max(1, int((end - start).total_seconds() * 1000))
        unit = "hour" if duration_ms <= 2 * DAY_MS else "day"
        return start, end, unit

    range_days = {"2d": 2, "3d": 3, "7d": 7, "14d": 14, "30d": 30, "90d": 90}.get(period, 7)
    start = _start_of_day(now - timedelta(days=range_days - 1))
    return start, now, "day"


def _format_bucket_label(bucket: datetime, unit: str) -> str:
    if unit == "hour":
        return bucket.strftime("%H:00")
    return bucket.strftime("%d %b")


@router.get("/analytics")
async def get_dashboard_analytics(
    period: str = Query("7d"),
    custom_start: str | None = Query(None),
    custom_end: str | None = Query(None),
    campaign_id: UUID | None = Query(None),
    client: dict = Depends(get_client_from_token),
    pool=Depends(get_pool),
):
    """Return a single analytics payload for the dashboard."""
    cid = client_id_uuid(client)

    campaigns = await pg_db.list_campaigns(pool, cid)
    if campaign_id is not None:
        campaigns = [c for c in (campaigns or []) if str(c.get("id")) == str(campaign_id)]

    interested_map = await pg_db.get_campaigns_interested_counts(pool, cid)

    total_campaigns = len(campaigns or [])
    running_campaigns = sum(
        1 for c in (campaigns or []) if (c.get("status") or "").lower() == "running"
    )
    interested_leads = sum(
        int(interested_map.get(str(c.get("id")), 0)) for c in (campaigns or [])
    )
    total_leads = sum(int(c.get("total_leads") or 0) for c in (campaigns or []))

    credits_used = 0.0
    for c in campaigns or []:
        credits_used += float(c.get("budget_used_credits") or c.get("credits_used") or 0)

    remaining_credits = float(client.get("balance_credits") or 0)
    total_credits = remaining_credits + credits_used
    live_calls = sum(int(c.get("calling_leads") or 0) for c in (campaigns or []))

    window_start, window_end, bucket_unit = _resolve_period_window(
        period, custom_start, custom_end
    )
    trunc = "hour" if bucket_unit == "hour" else "day"

    chart_args: list[Any] = [cid, window_start, window_end]
    campaign_filter = ""
    if campaign_id is not None:
        campaign_filter = f" AND campaign_id = ${len(chart_args) + 1}"
        chart_args.append(campaign_id)

    total_calls_row = await pool.fetchrow(
        f"""
        SELECT COUNT(*)::int AS total
        FROM call_logs
        WHERE client_id = $1
          AND started_at >= $2 AND started_at <= $3
          AND (call_data->>'is_test_call' IS NULL OR call_data->>'is_test_call' != 'true')
          {campaign_filter}
        """,
        *chart_args,
    )
    total_calls_in_period = int(total_calls_row["total"] or 0) if total_calls_row else 0

    calls_rows = await pool.fetch(
        f"""
        SELECT date_trunc('{trunc}', started_at) AS bucket, COUNT(*)::int AS calls
        FROM call_logs
        WHERE client_id = $1
          AND started_at >= $2 AND started_at <= $3
          AND (call_data->>'is_test_call' IS NULL OR call_data->>'is_test_call' != 'true')
          {campaign_filter}
        GROUP BY 1
        ORDER BY 1
        """,
        *chart_args,
    )

    interested_rows = await pool.fetch(
        f"""
        SELECT date_trunc('{trunc}', started_at) AS bucket, COUNT(*)::int AS interested
        FROM call_logs
        WHERE client_id = $1
          AND started_at >= $2 AND started_at <= $3
          AND outcome = 'Interested'
          AND (call_data->>'is_test_call' IS NULL OR call_data->>'is_test_call' != 'true')
          {campaign_filter}
        GROUP BY 1
        ORDER BY 1
        """,
        *chart_args,
    )

    interested_by_bucket = {
        _iso(r["bucket"]): int(r["interested"]) for r in interested_rows
    }
    chart_series = []
    for r in calls_rows:
        bucket_iso = _iso(r["bucket"])
        bucket_dt = r["bucket"]
        if isinstance(bucket_dt, str):
            bucket_dt = datetime.fromisoformat(bucket_dt.replace("Z", "+00:00"))
        chart_series.append(
            {
                "bucket": bucket_iso,
                "label": _format_bucket_label(bucket_dt, bucket_unit),
                "totalCalls": int(r["calls"]),
                "interested": interested_by_bucket.get(bucket_iso, 0),
            }
        )

    recent_calls, _ = await pg_db.list_call_logs(
        pool,
        cid,
        limit=50,
        offset=0,
        campaign_id=campaign_id,
    )

    activity = []
    for cl in recent_calls:
        if campaign_id is not None and str(cl.get("campaign_id")) != str(campaign_id):
            continue
        activity.append(
            {
                "id": cl.get("id") or cl.get("session_call_id"),
                "type": "call",
                "campaign_id": cl.get("campaign_id"),
                "campaign_name": cl.get("campaign_name") or cl.get("campaign") or None,
                "lead_name": cl.get("name") or cl.get("lead_name") or None,
                "outcome": cl.get("outcome") or cl.get("status") or None,
                "timestamp": _iso(
                    cl.get("started_at") or cl.get("created_at") or cl.get("ended_at")
                ),
                "credits_charged": float(
                    cl.get("credits_charged") or cl.get("credits_used") or 0
                ),
            }
        )

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

    activity = sorted(activity, key=lambda x: x.get("timestamp") or "", reverse=True)[:50]

    return {
        "summary": {
            "totalCampaigns": total_campaigns,
            "runningCampaigns": running_campaigns,
            "interestedLeads": int(interested_leads),
            "totalLeads": int(total_leads),
            "liveCalls": int(live_calls),
            "totalCalls": int(total_calls_in_period),
            "creditsUsed": float(credits_used),
            "remainingCredits": float(remaining_credits),
            "totalCredits": float(total_credits) if total_credits is not None else None,
        },
        "chart_series": chart_series,
        "recent_activity": activity,
        "campaigns": campaigns,
        "generated_at": datetime.now(UTC).isoformat(),
        "period": period,
    }
