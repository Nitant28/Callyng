import { useCallback, useMemo, useState } from 'react';
import clientApi from '../api/client';

const STARTABLE = new Set(['draft', 'paused', 'pausing']);
const ACTIVE = new Set(['running', 'pausing']);

const parseApiError = (err) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return err?.customErrorMessage || err?.message || 'Agent action failed';
};

export function useAgentControl(campaigns = [], { campaignId } = {}) {
  const [loading, setLoading] = useState(false);

  const scoped = useMemo(() => {
    if (!campaignId) return campaigns;
    return campaigns.filter((c) => String(c.id) === String(campaignId));
  }, [campaigns, campaignId]);

  const runningCampaign = useMemo(() => {
    const fromScope = scoped.find((c) => ACTIVE.has(c.status));
    if (fromScope) return fromScope;
    return campaigns.find((c) => ACTIVE.has(c.status)) || null;
  }, [scoped, campaigns]);

  const agentActive = Boolean(runningCampaign);
  const isPausing = runningCampaign?.status === 'pausing';
  const isRunning = runningCampaign?.status === 'running';

  const resolveStartTarget = useCallback(() => {
    if (campaignId) {
      const c = campaigns.find((x) => String(x.id) === String(campaignId));
      if (c && STARTABLE.has(c.status)) return c;
      return null;
    }
    const candidates = campaigns
      .filter((c) => STARTABLE.has(c.status) && (c.pendingLeads ?? 0) > 0)
      .sort((a, b) => (b.pendingLeads ?? 0) - (a.pendingLeads ?? 0));
    if (candidates.length) return candidates[0];
    return campaigns.find((c) => STARTABLE.has(c.status)) || null;
  }, [campaigns, campaignId]);

  const start = useCallback(async (onRefresh) => {
    const target = resolveStartTarget();
    if (!target) {
      throw new Error(campaignId
        ? 'This campaign cannot be started. Select a draft or paused campaign with pending leads.'
        : 'No campaign ready to start. Create a campaign or upload pending leads first.');
    }
    setLoading(true);
    try {
      await clientApi.patch(`/api/campaigns/${target.id}/start`);
      await onRefresh?.();
      return target;
    } catch (err) {
      throw new Error(parseApiError(err), { cause: err });
    } finally {
      setLoading(false);
    }
  }, [resolveStartTarget, campaignId]);

  const stop = useCallback(async (onRefresh) => {
    const target = runningCampaign;
    if (!target) {
      throw new Error('No active agent to stop.');
    }
    setLoading(true);
    try {
      await clientApi.patch(`/api/campaigns/${target.id}/stop`);
      await onRefresh?.();
      return target;
    } catch (err) {
      throw new Error(parseApiError(err), { cause: err });
    } finally {
      setLoading(false);
    }
  }, [runningCampaign]);

  const toggle = useCallback(async (onRefresh) => {
    if (agentActive && !isPausing) {
      return stop(onRefresh);
    }
    if (!agentActive) {
      return start(onRefresh);
    }
    return null;
  }, [agentActive, isPausing, start, stop]);

  return {
    agentActive,
    isPausing,
    isRunning,
    runningCampaign,
    start,
    stop,
    toggle,
    loading,
    canStart: Boolean(resolveStartTarget()),
  };
}

export default useAgentControl;
