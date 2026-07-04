/**
 * UI-only metrics derived from backend status values.
 * Never invent interested_leads, conversion, credits, or completion totals.
 */

export function countCampaignsByStatus(campaigns, status) {
  if (!Array.isArray(campaigns)) return 0;
  return campaigns.filter((c) => c.status === status).length;
}

export function countActiveCampaigns(campaigns) {
  return countCampaignsByStatus(campaigns, 'running');
}

export function countDraftCampaigns(campaigns) {
  return countCampaignsByStatus(campaigns, 'draft');
}

export function countPausedCampaigns(campaigns) {
  return countCampaignsByStatus(campaigns, 'paused');
}

export function shouldPollCampaigns(campaigns) {
  if (!Array.isArray(campaigns)) return false;
  return campaigns.some(
    (c) =>
      c.status === 'running' ||
      c.status === 'pausing' ||
      (c.status === 'paused' && (c.callingLeads ?? 0) > 0)
  );
}

/**
 * Sum interested_leads only when the backend exposes the field on campaign rows.
 */
export function sumInterestedLeadsIfPresent(campaigns) {
  if (!Array.isArray(campaigns) || campaigns.length === 0) return null;
  const hasField = campaigns.some((c) => c.interestedLeads != null);
  if (!hasField) return null;
  return campaigns.reduce((sum, c) => sum + (c.interestedLeads ?? 0), 0);
}
