import { isCallInProgress, parseTimestamp } from './helpers.js';

export const filterLiveCalls = (calls = []) =>
  calls.filter((call) => isCallInProgress(call));

export const filterRecentCalls = (calls = [], { minutes = 60 } = {}) => {
  const threshold = Date.now() - minutes * 60_000;
  return calls.filter((call) => {
    if (isCallInProgress(call)) return false;
    const timestamp = parseTimestamp(call);
    return timestamp !== null && timestamp >= threshold;
  });
};

export const groupCallsByCampaign = (calls = []) =>
  calls.reduce((groups, call) => {
    const campaignId = String(call.campaign_id || call.campaignId || 'unknown');
    const list = groups[campaignId] || [];
    list.push(call);
    groups[campaignId] = list;
    return groups;
  }, {});
