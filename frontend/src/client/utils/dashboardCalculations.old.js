const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;

const ACTIVE_OUTCOMES = new Set(['calling', 'in_progress']);
const INTERESTED_OUTCOMES = new Set(['interested']);
const ANSWERED_OUTCOMES = new Set(['interested', 'answered', 'completed', 'not_interested', 'early_disconnect', 'wrong_requirement']);

const priorityOrder = {
  calling: 1,
  ringing: 2,
  connecting: 2,
  busy: 3,
  callback_scheduled: 4,
  callback: 4,
  pending: 5,
  completed: 6,
  failed: 7,
};

const parseTimestamp = (call) => {
  const raw = call.started_at || call.created_at || call.startedAt || call.createdAt;
  if (!raw) return null;
  const t = new Date(raw).getTime();
  return Number.isNaN(t) ? null : t;
};

const normalizeOutcome = (rawOutcome, inProgress) => {
  const raw = (rawOutcome || '').toString().trim();
  if (inProgress === true) return 'in_progress';
  if (!raw) return 'completed';
  const lower = raw.toLowerCase();
  if (lower === 'calling') return 'calling';
  if (lower === 'interested') return 'interested';
  if (lower === 'not_interested') return 'not_interested';
  if (lower === 'no_answer' || lower === 'noanswer' || lower === 'voicemail') return 'no_answer';
  if (lower === 'busy') return 'busy';
  if (lower === 'callback' || lower === 'callback_requested' || lower === 'callback_scheduled') return 'callback';
  if (lower === 'early_disconnect' || lower === 'earlydisconnect') return 'early_disconnect';
  if (lower.includes('carrier') || lower.includes('failed')) return 'carrier_failed';
  if (lower === 'answered' || lower === 'answer') return 'answered';
  if (lower === 'wrong_requirement' || lower === 'wrong_number' || lower === 'wrong number') return 'wrong_requirement';
  return lower.replace(/_/g, ' ') || 'completed';
};

const getLabelFromOutcome = (outcome) => {
  switch (outcome) {
    case 'calling': return 'Live Call';
    case 'in_progress': return 'Call in Progress';
    case 'interested': return 'Interested';
    case 'not_interested': return 'Not Interested';
    case 'no_answer': return 'No Answer';
    case 'busy': return 'Busy';
    case 'callback': return 'Callback';
    case 'early_disconnect': return 'Hung Up Early';
    case 'carrier_failed': return 'Carrier Failed';
    case 'answered': return 'Answered';
    case 'wrong_requirement': return 'Wrong Requirement';
    default: return 'Call Ended';
  }
};

const formatRelativeTime = (iso) => {
  if (!iso) return 'Unknown';
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 60_000) return 'Just now';
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

const getDayKey = (timestamp) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
};

const getHourKey = (timestamp) => {
  const date = new Date(timestamp);
  return `${String(date.getHours()).padStart(2, '0')}:00`;
};

const getRangeWindow = (period, customStart, customEnd) => {
  const now = Date.now();

  if (period === 'today') {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return { start: start.getTime(), end: now, unit: 'hour' };
  }

  if (period === 'yesterday') {
    const start = new Date();
    start.setDate(start.getDate() - 1);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return { start: start.getTime(), end: end.getTime(), unit: 'hour' };
  }

  if (period === 'custom' && customStart && customEnd) {
    const start = new Date(customStart);
    start.setHours(0, 0, 0, 0);
    const end = new Date(customEnd);
    end.setHours(23, 59, 59, 999);
    const durationDays = Math.max(1, Math.ceil((end.getTime() - start.getTime()) / DAY_MS));
    return { start: start.getTime(), end: end.getTime(), unit: durationDays <= 2 ? 'hour' : 'day' };
  }

  const rangeDays = {
    '2d': 2,
    '3d': 3,
    '7d': 7,
    '14d': 14,
    '30d': 30,
    '90d': 90,
  }[period] || 7;

  return { start: now - rangeDays * DAY_MS, end: now, unit: 'day', days: rangeDays };
};

const filterCallsByPeriod = (calls, period, customStart, customEnd) => {
  if (!Array.isArray(calls)) return [];
  const { start, end } = getRangeWindow(period, customStart, customEnd);
  return calls.filter((call) => {
    const ts = parseTimestamp(call);
    return ts != null && ts >= start && ts <= end;
  });
};

const buildChartData = (calls, period, customStart, customEnd) => {
  const { start, end, unit, days } = getRangeWindow(period, customStart, customEnd);
  const buckets = new Map();
  const bucketKeys = [];

  if (unit === 'hour') {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const hours = Math.ceil((endDate.getTime() - startDate.getTime()) / HOUR_MS);
    for (let i = 0; i <= hours; i += 1) {
      const date = new Date(startDate.getTime() + i * HOUR_MS);
      const label = getHourKey(date.getTime());
      buckets.set(label, 0);
      bucketKeys.push(label);
    }
  } else {
    const totalDays = days || Math.ceil((end - start) / DAY_MS);
    for (let i = 0; i <= totalDays; i += 1) {
      const date = new Date(start + i * DAY_MS);
      const label = getDayKey(date.getTime());
      buckets.set(label, 0);
      bucketKeys.push(label);
    }
  }

  calls.forEach((call) => {
    const timestamp = parseTimestamp(call);
    if (timestamp == null) return;

    const normalized = normalizeOutcome(call.outcome || call.outcome_raw, call.in_progress || call.inProgress);
    if (!INTERESTED_OUTCOMES.has(normalized)) return;

    const label = unit === 'hour' ? getHourKey(timestamp) : getDayKey(timestamp);
    if (!buckets.has(label)) return;
    buckets.set(label, buckets.get(label) + 1);
  });

  return bucketKeys.map((label) => ({ label, calls: buckets.get(label) ?? 0 }));
};

const sortCallsByPriority = (calls) => {
  if (!Array.isArray(calls)) return [];
  return [...calls].sort((a, b) => {
    const aNorm = normalizeOutcome(a.outcome || a.outcome_raw, a.in_progress || a.inProgress);
    const bNorm = normalizeOutcome(b.outcome || b.outcome_raw, b.in_progress || b.inProgress);
    const aPriority = priorityOrder[aNorm] ?? 99;
    const bPriority = priorityOrder[bNorm] ?? 99;
    if (aPriority !== bPriority) return aPriority - bPriority;
    const aTime = parseTimestamp(a) || 0;
    const bTime = parseTimestamp(b) || 0;
    return bTime - aTime;
  });
};

const mapActivityEvent = (call) => {
  const outcome = normalizeOutcome(call.outcome || call.outcome_raw, call.in_progress || call.inProgress);
  const title = getLabelFromOutcome(outcome);

  return {
    id: call.session_call_id || call.id || `${call.lead_id || 'lead'}-${parseTimestamp(call) || ''}`,
    title,
    leadName: call.lead_name || call.name || call.lead || call.caller_name || call.lead_phone || call.phone || 'Unknown',
    campaignName: call.campaign_name || call.campaign || call.campaignName || '—',
    duration: call.duration || call.duration_seconds || call.call_duration || call.last_call_duration_seconds || null,
    creditsUsed: Number(call.credits_used ?? call.credits_charged ?? call.creditsUsed ?? 0),
    attemptNumber: call.attempt_number || call.attempts || 1,
    outcome,
    time: formatRelativeTime(call.started_at || call.created_at || call.startedAt || call.createdAt),
    isLive: ACTIVE_OUTCOMES.has(outcome),
  };
};

const sumCampaignField = (campaigns, field) =>
  (Array.isArray(campaigns) ? campaigns : []).reduce((sum, campaign) => sum + Number(campaign[field] || 0), 0);

const hasCampaignField = (campaigns, field) =>
  Array.isArray(campaigns) && campaigns.some((campaign) => campaign[field] != null);

const calculateDashboardMetrics = (campaigns, calls, balance = 0) => {
  const runningCampaigns = Array.isArray(campaigns)
    ? campaigns.filter((c) => c.status === 'running').length
    : 0;

  const interestedLeadsFromCampaigns = hasCampaignField(campaigns, 'interested_leads')
    ? sumCampaignField(campaigns, 'interested_leads')
    : hasCampaignField(campaigns, 'interestedLeads')
      ? sumCampaignField(campaigns, 'interestedLeads')
      : null;

  const answeredLeadsFromCampaigns = hasCampaignField(campaigns, 'answered_leads')
    ? sumCampaignField(campaigns, 'answered_leads')
    : hasCampaignField(campaigns, 'answeredLeads')
      ? sumCampaignField(campaigns, 'answeredLeads')
      : null;

  const creditsUsedFromCampaigns = hasCampaignField(campaigns, 'credits_used')
    ? sumCampaignField(campaigns, 'credits_used')
    : hasCampaignField(campaigns, 'creditsUsed')
      ? sumCampaignField(campaigns, 'creditsUsed')
      : hasCampaignField(campaigns, 'budget_used_credits')
        ? sumCampaignField(campaigns, 'budget_used_credits')
        : hasCampaignField(campaigns, 'budgetUsed')
          ? sumCampaignField(campaigns, 'budgetUsed')
          : null;

  let interestedLeads = interestedLeadsFromCampaigns;
  let answeredLeads = answeredLeadsFromCampaigns;
  let creditsUsed = creditsUsedFromCampaigns;
  let activeCallsCount = 0;

  calls.forEach((call) => {
    const outcome = normalizeOutcome(call.outcome || call.outcome_raw, call.in_progress || call.inProgress);
    if (ACTIVE_OUTCOMES.has(outcome)) activeCallsCount += 1;

    if (interestedLeads == null && INTERESTED_OUTCOMES.has(outcome)) {
      interestedLeads = (interestedLeads || 0) + 1;
    }
    if (answeredLeads == null && ANSWERED_OUTCOMES.has(outcome)) {
      answeredLeads = (answeredLeads || 0) + 1;
    }
    if (creditsUsed == null) {
      creditsUsed = Number(call.credits_used ?? call.credits_charged ?? call.creditsUsed ?? 0) + (creditsUsed || 0);
    }
  });

  const remainingCredits = Number(balance ?? 0);
  const usedCredits = Number(creditsUsed ?? 0);
  const totalCredits = remainingCredits + usedCredits;
  const remainingPercent = totalCredits > 0 ? Math.round((remainingCredits / totalCredits) * 100) : 0;

  return {
    runningCampaigns,
    interestedLeads: interestedLeads ?? 0,
    answeredLeads: answeredLeads ?? 0,
    creditsUsed: usedCredits,
    remainingCredits,
    totalCredits,
    remainingPercent,
    activeCallsCount,
    totalCallsCount: calls.length,
    conversionRate: answeredLeads > 0 ? ((interestedLeads / answeredLeads) * 100).toFixed(1) : '0.0',
  };
};

export const calculateDashboardView = ({
  balance = 0,
  campaigns = [],
  calls = [],
  period = '7d',
  customStart = null,
  customEnd = null,
} = {}) => {
  const filteredCalls = filterCallsByPeriod(calls, period, customStart, customEnd);
  const chartData = buildChartData(filteredCalls, period, customStart, customEnd);
  const activityEvents = sortCallsByPriority(calls)
    .slice(0, 30)
    .map(mapActivityEvent);
  const metrics = calculateDashboardMetrics(campaigns, calls, balance);

  return {
    filteredCalls,
    chartData,
    activityEvents,
    metrics,
  };
};
