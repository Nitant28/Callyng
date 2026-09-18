import { useCallback, useEffect, useMemo, useState } from 'react';
import clientApi from '../api/client';
import { useDashboardData } from '../contexts/DashboardDataContext';
import { mapCampaignRows } from '../utils/campaignHelpers';

export function useCampaigns() {
  const {
    campaigns: rawCampaigns,
    loading,
    refreshing,
    refresh,
  } = useDashboardData();

  const campaigns = useMemo(() => mapCampaignRows(rawCampaigns), [rawCampaigns]);
  const [error, setError] = useState(null);
  const [botOptions, setBotOptions] = useState([]);

  const loadBots = useCallback(async (rows) => {
    const ids = [...new Set(rows.map((r) => r.bot_config_id).filter(Boolean))];
    if (!ids.length) {
      setBotOptions([]);
      return;
    }
    const bots = [];
    await Promise.all(
      ids.slice(0, 10).map(async (botId) => {
        const camp = rows.find((r) => r.bot_config_id === botId);
        if (!camp?.id) return;
        try {
          const res = await clientApi.get(`/api/campaigns/${camp.id}/stats`);
          const bot = res.data?.stats?.bot_config;
          if (bot) {
            bots.push({
              id: bot.id || botId,
              name: bot.name || bot.script_id || 'Voice Agent',
              scriptId: bot.script_id,
            });
          }
        } catch {
          bots.push({ id: botId, name: `Agent ${String(botId).slice(0, 8)}` });
        }
      }),
    );
    const unique = [];
    const seen = new Set();
    bots.forEach((b) => {
      if (!seen.has(b.id)) {
        seen.add(b.id);
        unique.push(b);
      }
    });
    setBotOptions(unique);
  }, []);

  useEffect(() => {
    setError(null);
    loadBots(rawCampaigns || []).catch(() => {
      setError('Unable to load voice agents.');
    });
  }, [rawCampaigns, loadBots]);

  const createCampaign = useCallback(async (payload) => {
    const res = await clientApi.post('/api/campaigns', payload);
    await refresh();
    return res.data?.id;
  }, [refresh]);

  const startCampaign = useCallback(async (id) => {
    await clientApi.patch(`/api/campaigns/${id}/start`);
    await refresh();
  }, [refresh]);

  const stopCampaign = useCallback(async (id) => {
    await clientApi.patch(`/api/campaigns/${id}/stop`);
    await refresh();
  }, [refresh]);

  const cancelCampaign = useCallback(async (id) => {
    await clientApi.patch(`/api/campaigns/${id}/cancel`);
    await refresh();
  }, [refresh]);

  const uploadLeads = useCallback(async (id, file) => {
    const form = new FormData();
    form.append('file', file);
    await clientApi.post(`/api/campaigns/${id}/leads/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    await refresh();
  }, [refresh]);

  const duplicateCampaign = useCallback(
    async (campaign) => {
      const id = await createCampaign({
        name: `${campaign.name} (copy)`,
        bot_config_id: campaign.botConfigId,
        budget_credits: campaign.budgetCredits || 0,
        max_concurrent_calls: campaign.maxConcurrentCalls || 5,
        calls_per_minute: campaign.callsPerMinute || 10,
        max_attempts: campaign.maxAttempts || 3,
        retry_delay_minutes: campaign.retryDelayMinutes || 120,
      });
      return id;
    },
    [createCampaign],
  );

  return {
    campaigns,
    loading,
    refreshing,
    error,
    botOptions,
    refresh,
    createCampaign,
    startCampaign,
    stopCampaign,
    cancelCampaign,
    uploadLeads,
    duplicateCampaign,
  };
}
