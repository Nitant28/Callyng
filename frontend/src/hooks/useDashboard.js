import { useState, useEffect, useCallback, useRef } from 'react';
import clientApi from '../api/client';
import { mapCredits, mapCampaigns, mapCalls } from '../utils/dashboardMapper';
import { shouldPollCampaigns } from '../utils/dashboardCalculations';

const LIVE_POLL_MS = 10000;

const EMPTY_ERROR = { credits: null, campaigns: null, calls: null };

export function useDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(EMPTY_ERROR);
  const [credits, setCredits] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [calls, setCalls] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshLatencyMs, setRefreshLatencyMs] = useState(null);
  const refreshStart = useRef(0);

  const refresh = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    refreshStart.current = performance.now();

    const [creditsResult, campaignsResult, callsResult] = await Promise.allSettled([
      clientApi.get('/api/credits'),
      clientApi.get('/api/campaigns'),
      clientApi.get('/api/calls', { params: { limit: 50, offset: 0 } }),
    ]);

    setRefreshLatencyMs(Math.round(performance.now() - refreshStart.current));
    setLastUpdated(new Date().toISOString());

    const nextError = { ...EMPTY_ERROR };

    if (creditsResult.status === 'fulfilled') {
      setCredits(mapCredits(creditsResult.value.data));
      if (creditsResult.value.data?.client_name) {
        localStorage.setItem('client_name', creditsResult.value.data.client_name);
      }
    } else {
      nextError.credits = 'Unable to load credits.';
      setCredits(null);
    }

    if (campaignsResult.status === 'fulfilled') {
      const rows = campaignsResult.value.data?.campaigns ?? [];
      setCampaigns(mapCampaigns(rows));
    } else {
      nextError.campaigns = 'Unable to load campaigns.';
      setCampaigns([]);
    }

    if (callsResult.status === 'fulfilled') {
      setCalls(mapCalls(callsResult.value.data?.calls ?? []));
    } else {
      nextError.calls = 'Unable to load recent activity.';
      setCalls([]);
    }

    setError(nextError);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh(true);
  }, [refresh]);

  useEffect(() => {
    const interval = setInterval(() => {
      refresh(false);
    }, LIVE_POLL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    if (!shouldPollCampaigns(campaigns)) return undefined;

    const interval = setInterval(() => {
      refresh(false);
    }, 5000);

    return () => clearInterval(interval);
  }, [campaigns, refresh]);

  return {
    loading,
    error,
    credits,
    campaigns,
    calls,
    lastUpdated,
    refreshLatencyMs,
    refresh: () => refresh(false),
  };
}
