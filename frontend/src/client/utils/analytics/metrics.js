import {
  getCampaignField,
  isAnsweredOutcome,
  isCallInProgress,
  isInterestedOutcome,
  safeNumber,
  sumCampaignField,
} from './helpers.js';

const countCalls = (calls, predicate) =>
  (calls ?? []).reduce((count, call) => (predicate(call) ? count + 1 : count), 0);

export const buildKpiMetrics = ({ campaigns = [], calls = [], balance = {} }) => {
  const interestedLeads = sumCampaignField(campaigns, 'interested_leads');

  const totalLeads = sumCampaignField(campaigns, 'total_leads');

  const inProgressCount = countCalls(calls, isCallInProgress);
  const callingFromCampaigns = sumCampaignField(campaigns, 'calling_leads');
  const liveCalls = Math.max(inProgressCount, callingFromCampaigns);

  const creditsUsed = sumCampaignField(campaigns, 'budget_used_credits');

  // Admin wallet balance (clients.balance_credits) — same source as admin panel
  const remainingCredits = safeNumber(balance.balance_credits ?? balance.balanceCredits ?? 0);
  const totalCredits = remainingCredits + creditsUsed;
  const remainingPercent =
    totalCredits > 0 ? Math.round((remainingCredits / totalCredits) * 100) : 0;

  return {
    runningCampaigns: campaigns.filter((c) => c.status === 'running').length,
    interestedLeads,
    totalLeads,
    creditsUsed,
    totalCredits,
    remainingCredits,
    remainingPercent,
    totalCampaigns: campaigns.length,
    liveCalls,
    totalCalls: calls.length,
  };
};

export const buildCampaignSummary = ({ campaigns = [], calls = [] }) => {
  const callStats = {};

  (calls ?? []).forEach((call) => {
    const campaignId = String(call.campaign_id || call.campaignId || 'unknown');
    const stats = callStats[campaignId] || { interested: 0, answered: 0, credits: 0 };
    if (isInterestedOutcome(call)) stats.interested += 1;
    if (isAnsweredOutcome(call)) stats.answered += 1;
    stats.credits += safeNumber(call.credits_charged ?? call.credits_used ?? 0);
    callStats[campaignId] = stats;
  });

  return campaigns.map((campaign) => {
    const id = String(campaign.id);
    const fromCalls = callStats[id] || { interested: 0, answered: 0, credits: 0 };

    const interested = getCampaignField(campaign, 'interested_leads');
    const answered =
      getCampaignField(campaign, 'answered_leads') || fromCalls.answered;
    const creditsUsed = getCampaignField(campaign, 'budget_used_credits') || fromCalls.credits;
    const totalLeads = getCampaignField(campaign, 'total_leads');
    const conversion =
      campaign.conversion_rate != null
        ? campaign.conversion_rate
        : totalLeads > 0
          ? Math.round((interested / totalLeads) * 1000) / 10
          : answered > 0
            ? Math.round((interested / answered) * 1000) / 10
            : 0;

    return {
      campaignId: campaign.id,
      campaignName: campaign.name || campaign.title || 'Unknown campaign',
      status: campaign.status,
      interested,
      answered,
      creditsUsed,
      conversion,
      callingLeads: getCampaignField(campaign, 'calling_leads'),
      totalLeads,
      updatedAt: campaign.updated_at || campaign.completed_at || campaign.created_at,
      createdAt: campaign.created_at,
    };
  });
};
