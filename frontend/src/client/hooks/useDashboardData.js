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

const enrichCampaignsWithStats = async (campaigns) => {
  if (!campaigns.length) return [];

  return Promise.all(
    campaigns.map(async (camp) => {
      try {
        const res = await clientApi.get(`/api/campaigns/${camp.id}/stats`);
        const stats = res.data?.stats || {};
        return {
          ...camp,
          interested_leads: stats.interested_leads ?? camp.interested_leads ?? 0,
          answered_leads: stats.answered_leads ?? camp.answered_leads ?? 0,
          calling_leads: stats.calling_leads ?? camp.calling_leads ?? 0,
          completed_leads: stats.completed_leads ?? camp.completed_leads ?? 0,
          conversion_rate: stats.conversion_rate ?? camp.conversion_rate ?? null,
          budget_used_credits: stats.budget_used_credits ?? camp.budget_used_credits ?? 0,
        };
      } catch {
        return camp;
      }
    }),
  );
};

/** Global call log + per-campaign calls merged (deduped). */
const fetchAllCalls = async (campaignList = []) => {
  const requests = [
    clientApi.get('/api/calls', { params: { limit: 2000 } }),
  ];

  campaignList.forEach((camp) => {
    requests.push(
      clientApi.get(`/api/campaigns/${camp.id}/calls`, { params: { limit: 200 } }),
    );
  });

  const results = await Promise.allSettled(requests);
  const merged = [];

  results.forEach((result) => {
    if (result.status === 'fulfilled') {
      merged.push(...(result.value.data?.calls || []));
    }
  });

  return dedupeCalls(merged);
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
      const res = await clientApi.get('/api/campaigns');
      const list = res.data?.campaigns || [];
      campaignsRef.current = list;
      setCampaigns(list);
      const enriched = await enrichCampaignsWithStats(list);
      campaignsRef.current = enriched;
      setCampaigns(enriched);
      return list;
    } catch {
      setCampaigns([]);
      campaignsRef.current = [];
      return [];
    }
  }, []);

  const loadCalls = useCallback(async (campaignList) => {
    try {
      const list = campaignList ?? campaignsRef.current;
      const merged = await fetchAllCalls(list);
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
    const list = await loadCampaigns();
    await loadCalls(list);

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

      const list = await loadCampaigns();
      await loadCalls(list);
      if (!cancelled) {
        timer = setTimeout(poll, isLive ? 2000 : 5000);
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
