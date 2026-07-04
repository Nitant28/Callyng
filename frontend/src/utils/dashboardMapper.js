/**
 * Rename backend fields → frontend model. No calculations.
 */

export function mapCredits(data) {
  if (!data) return null;
  return {
    balanceCredits: data.balance_credits ?? null,
    maxConcurrentCalls: data.max_concurrent_calls ?? null,
    clientName: data.client_name ?? null,
    conversionRate: data.conversion_rate ?? null,
    costPerLead: data.cost_per_lead ?? null,
  };
}

export function mapCampaign(row) {
  if (!row) return null;
  return {
    id: row.id,
    title: row.name,
    status: row.status,
    totalLeads: row.total_leads ?? 0,
    interestedLeads: row.interested_leads ?? null,
    creditsUsed: row.budget_used_credits ?? 0,
    budgetCredits: row.budget_credits ?? 0,
    callingLeads: row.calling_leads ?? 0,
    pendingLeads: row.pending_leads ?? 0,
    completedLeads: row.completed_leads ?? 0,
    failedLeads: row.failed_leads ?? 0,
    createdAt: row.created_at ?? null,
  };
}

export function mapCampaigns(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.map(mapCampaign).filter(Boolean);
}

export function mapCall(row) {
  if (!row) return null;
  return {
    sessionCallId: row.session_call_id,
    leadId: row.lead_id ?? null,
    leadName: row.name ?? 'Unknown',
    leadPhone: row.phone ?? '',
    outcome: row.outcome ?? null,
    durationSeconds: row.duration_seconds ?? null,
    createdAt: row.created_at ?? null,
    startedAt: row.started_at ?? null,
    inProgress: row.in_progress === true,
    campaignId: row.campaign_id ?? null,
  };
}

export function mapCalls(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.map(mapCall).filter(Boolean);
}
