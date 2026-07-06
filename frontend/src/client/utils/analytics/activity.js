import {
  formatClockTime,
  formatRelativeTime,
  getCampaignField,
  isCallInProgress,
  normalizeOutcome,
  outcomeLabel,
  parseTimestamp,
  safeNumber,
  sortCallsForDisplay,
  statusTone,
} from './helpers.js';

const formatCallEvent = (call, campaignName) => {
  const inProgress = isCallInProgress(call);
  const outcome = normalizeOutcome(call.outcome || call.status, inProgress);
  const ts = parseTimestamp(call);
  const timestamp = ts != null ? new Date(ts).toISOString() : (call.started_at || call.created_at);

  return {
    id: call.session_call_id || call.id || `${call.campaign_id}-${call.lead_id}-${timestamp}`,
    campaignId: call.campaign_id || call.campaignId,
    campaignName: campaignName || call.campaign_name || 'Unknown campaign',
    leadName: call.name || call.lead_name || 'Unknown lead',
    leadPhone: call.phone || call.phone_number || '',
    outcome,
    tone: statusTone(call),
    title: outcomeLabel(call),
    isLive: inProgress,
    timestamp,
    clock: formatClockTime(timestamp),
    relativeTime: formatRelativeTime(timestamp),
    time: inProgress ? 'Live' : formatRelativeTime(timestamp),
    attemptNumber: call.attempt_number || call.attempts || null,
    duration: safeNumber(call.duration_seconds ?? call.duration) || null,
    creditsUsed: safeNumber(call.credits_charged ?? call.credits_used),
  };
};

export const buildLiveActivity = (calls = [], campaigns = []) => {
  const campaignNames = (campaigns ?? []).reduce((map, campaign) => {
    if (campaign?.id) {
      map[String(campaign.id)] = campaign.name || campaign.title || 'Unknown campaign';
    }
    return map;
  }, {});

  const sorted = sortCallsForDisplay(calls);
  const live = sorted.filter(isCallInProgress);
  const recent = sorted.filter((c) => !isCallInProgress(c)).slice(0, 25);

  const seen = new Set();
  const events = [];

  [...live, ...recent].forEach((call) => {
    const event = formatCallEvent(call, campaignNames[String(call.campaign_id || call.campaignId)]);
    if (!seen.has(event.id)) {
      seen.add(event.id);
      events.push(event);
    }
  });

  (campaigns ?? []).forEach((campaign) => {
    const calling = getCampaignField(campaign, 'calling_leads');
    if (calling <= 0 || campaign.status !== 'running') return;

    const timestamp = campaign.updated_at || campaign.created_at || new Date().toISOString();
    const id = `campaign-live-${campaign.id}`;
    if (seen.has(id)) return;

    events.unshift({
      id,
      campaignId: campaign.id,
      campaignName: campaign.name || campaign.title || 'Unknown campaign',
      leadName: `${calling} active dial${calling === 1 ? '' : 's'}`,
      leadPhone: '',
      outcome: 'calling',
      tone: 'live',
      title: 'Dialer running',
      isLive: true,
      timestamp,
      clock: 'Now',
      relativeTime: 'Live',
      time: 'Live',
      attemptNumber: null,
      duration: null,
      creditsUsed: 0,
    });
    seen.add(id);
  });

  return events.sort((a, b) => {
    if (a.isLive !== b.isLive) return a.isLive ? -1 : 1;
    return new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime();
  });
};
