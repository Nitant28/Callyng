import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import clientApi from '../api/client';
import { useDashboardData } from './DashboardDataContext';

const CampaignWorkspaceContext = createContext(null);

export const useCampaignWorkspace = () => {
  const ctx = useContext(CampaignWorkspaceContext);
  if (!ctx) throw new Error('useCampaignWorkspace must be used within CampaignWorkspaceProvider');
  return ctx;
};

export const CampaignWorkspaceProvider = ({ campaignId, children }) => {
  const { refresh: refreshDashboard } = useDashboardData();
  const [campaign, setCampaign] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isReleasingStuck, setIsReleasingStuck] = useState(false);
  const [leadSearch, setLeadSearch] = useState('');

  const loadCampaign = useCallback(async (spinner = true) => {
    if (!campaignId) return;
    if (spinner) setLoading(true);
    try {
      const response = await clientApi.get(`/api/campaigns/${campaignId}/stats`);
      setCampaign(response.data?.stats ?? null);
    } catch {
      setCampaign(null);
    } finally {
      if (spinner) setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    const t = setTimeout(() => loadCampaign(), 0);
    return () => clearTimeout(t);
  }, [loadCampaign]);

  useEffect(() => {
    if (!campaign) return undefined;
    const isPausing =
      campaign.status === 'pausing' ||
      (campaign.status === 'paused' && (campaign.calling_leads ?? 0) > 0);
    if (campaign.status !== 'running' && !isPausing) return undefined;
    const pollInterval = isPausing ? 2000 : 5000;
    const interval = setInterval(() => loadCampaign(false), pollInterval);
    return () => clearInterval(interval);
  }, [campaign, loadCampaign]);

  const refreshCampaign = useCallback(async () => {
    await loadCampaign(false);
    refreshDashboard?.();
  }, [loadCampaign, refreshDashboard]);

  const voiceAgentName =
    campaign?.bot_config?.name || campaign?.bot_config?.script_id || 'Voice Agent';

  const isPausing =
    campaign?.status === 'pausing' ||
    (campaign?.status === 'paused' && (campaign?.calling_leads ?? 0) > 0);

  const value = useMemo(
    () => ({
      campaignId,
      campaign,
      loading,
      isPausing,
      isReleasingStuck,
      setIsReleasingStuck,
      voiceAgentName,
      leadSearch,
      setLeadSearch,
      refreshCampaign,
      loadCampaign,
    }),
    [
      campaignId,
      campaign,
      loading,
      isPausing,
      isReleasingStuck,
      voiceAgentName,
      leadSearch,
      refreshCampaign,
      loadCampaign,
    ],
  );

  return (
    <CampaignWorkspaceContext.Provider value={value}>
      {children}
    </CampaignWorkspaceContext.Provider>
  );
};
