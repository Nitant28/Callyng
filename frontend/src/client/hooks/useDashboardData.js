import { useState, useEffect, useCallback, useRef } from 'react';
import clientApi from '../../api/client';

const sortCalls = (calls) =>
  [...calls].sort((a, b) => {
    const liveA = a.in_progress === true;
    const liveB = b.in_progress === true;
    if (liveA !== liveB) return liveA ? -1 : 1;
    const ta = new Date(a.ended_at || a.started_at || a.created_at || 0).getTime();
    const tb = new Date(b.ended_at || b.started_at || b.created_at || 0).getTime();
    return tb - ta;
  });

const dedupeCalls = (rows) => {
  const map = new Map();
  (rows || []).forEach((call) => {
    const key = call.session_call_id || call.id;
    if (key) map.set(key, call);
  });
  return sortCalls([...map.values()]);
};

/** Recent calls from the global list endpoint (no per-campaign fan-out). */
const fetchAllCalls = async () => {
  const res = await clientApi.get('/api/calls', { params: { limit: 100 } });
  return dedupeCalls(res.data?.calls || []);
};

const useDashboardData = () => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [balance, setBalance] = useState({});
  const [campaigns, setCampaigns] = useState([]);
  const [calls, setCalls] = useState([]);
  const [totalCalls, setTotalCalls] = useState(0);

  const campaignsRef = useRef([]);

  useEffect(() => {
    campaignsRef.current = campaigns;
  }, [campaigns]);

  const loadBalance = useCallback(async () => {
    try {
      const res = await clientApi.get('/api/credits');
      setBalance(res.data || {});
    } catch {
      /* keep stale */
    }
  }, []);

  const loadCampaigns = useCallback(async () => {
    try {
      // list_campaigns already attaches interested_leads + conversion_rate
      // and denorm status counters — no N+1 /stats enrichment on the home dash.
      const res = await clientApi.get('/api/campaigns');
      const list = res.data?.campaigns || [];
      campaignsRef.current = list;
      setCampaigns(list);
      return list;
    } catch {
      setCampaigns([]);
      campaignsRef.current = [];
      return [];
    }
  }, []);

  const loadCalls = useCallback(async () => {
    try {
      const merged = await fetchAllCalls();
      setCalls(merged);
      setTotalCalls(merged.length);
    } catch (err) {
      console.error('[dashboard] calls load failed', err);
      setCalls([]);
      setTotalCalls(0);
    }
  }, []);

  const loadAll = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);

    await loadBalance();
    await loadCampaigns();
    await loadCalls();

    setLoading(false);
    setRefreshing(false);
  }, [loadBalance, loadCampaigns, loadCalls]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    loadBalance();
    const id = setInterval(loadBalance, 10_000);
    return () => clearInterval(id);
  }, [loadBalance]);

  useEffect(() => {
    let timer;
    let cancelled = false;

    const poll = async () => {
      const current = campaignsRef.current;
      const isLive = current.some(
        (c) =>
          c.status === 'running' ||
          c.status === 'pausing' ||
          (c.status === 'paused' && (c.calling_leads || 0) > 0),
      );

      await loadCampaigns();
      await loadCalls();
      if (!cancelled) {
        timer = setTimeout(poll, isLive ? 5000 : 15000);
      }
    };

    timer = setTimeout(poll, 5000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [loadCampaigns, loadCalls]);

  return {
    loading,
    refreshing,
    balance,
    campaigns,
    calls,
    totalCalls,
    refresh: () => loadAll({ silent: true }),
  };
};

export default useDashboardData;
