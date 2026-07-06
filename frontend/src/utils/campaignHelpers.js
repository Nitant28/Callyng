import { computeCampaignHealth } from './dashboardKpis';

export function mapCampaignRow(row) {
  if (!row) return null;
  const budget = row.budget_credits ?? 0;
  const used = row.budget_used_credits ?? 0;
  const remaining = budget > 0 ? Math.max(0, budget - used) : null;
  const totalLeads = row.total_leads ?? 0;
  const completed = row.completed_leads ?? 0;
  const health = computeCampaignHealth({
    totalLeads,
    interestedLeads: row.interested_leads ?? null,
    completedLeads: completed,
    status: row.status,
  });

  return {
    id: row.id,
    name: row.name || 'Untitled',
    status: row.status || 'draft',
    botConfigId: row.bot_config_id,
    totalLeads,
    interestedLeads: row.interested_leads ?? null,
    notInterestedLeads: row.not_interested_leads ?? null,
    busyLeads: row.busy_leads ?? null,
    completedLeads: completed,
    failedLeads: row.failed_leads ?? 0,
    callingLeads: row.calling_leads ?? 0,
    pendingLeads: row.pending_leads ?? 0,
    callbackLeads: row.callback_leads ?? 0,
    budgetCredits: budget,
    creditsUsed: used,
    creditsRemaining: remaining,
    maxConcurrentCalls: row.max_concurrent_calls ?? null,
    callsPerMinute: row.calls_per_minute ?? null,
    maxAttempts: row.max_attempts ?? null,
    retryDelayMinutes: row.retry_delay_minutes ?? null,
    createdAt: row.created_at,
    health,
    leadProgressPct: totalLeads > 0 ? Math.round((completed / totalLeads) * 100) : 0,
    budgetProgressPct: budget > 0 ? Math.min(100, Math.round((used / budget) * 100)) : null,
    successRatePct: totalLeads > 0 ? Math.round((completed / totalLeads) * 100) : null,
    conversionRate: row.conversion_rate ?? null,
  };
}

export function mapCampaignRows(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.map(mapCampaignRow).filter(Boolean);
}

export function statusTone(status) {
  const s = (status || '').toLowerCase();
  if (s === 'running') return 'success';
  if (s === 'paused' || s === 'pausing') return 'warning';
  if (s === 'completed') return 'info';
  if (s === 'cancelled' || s === 'failed') return 'danger';
  return 'neutral';
}

export function statusLabel(status) {
  const labels = {
    running: 'Running',
    paused: 'Paused',
    pausing: 'Pausing',
    draft: 'Draft',
    completed: 'Completed',
    cancelled: 'Cancelled',
    failed: 'Failed',
  };
  return labels[(status || '').toLowerCase()] || status || 'Unknown';
}

export function formatCampaignDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

export function filterCampaigns(campaigns, { tab, search, status }) {
  let list = [...campaigns];
  if (tab && tab !== 'all') {
    list = list.filter((c) => {
      if (tab === 'paused') return c.status === 'paused' || c.status === 'pausing';
      return c.status === tab;
    });
  }
  if (status) {
    list = list.filter((c) => c.status === status);
  }
  if (search?.trim()) {
    const q = search.trim().toLowerCase();
    list = list.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        String(c.id).toLowerCase().includes(q),
    );
  }
  return list;
}

export function sortCampaigns(campaigns, sortBy) {
  const list = [...campaigns];
  switch (sortBy) {
    case 'name':
      return list.sort((a, b) => a.name.localeCompare(b.name));
    case 'oldest':
      return list.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
    case 'credits':
      return list.sort((a, b) => (b.creditsUsed ?? 0) - (a.creditsUsed ?? 0));
    case 'leads':
      return list.sort((a, b) => (b.totalLeads ?? 0) - (a.totalLeads ?? 0));
    default:
      return list.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }
}

export function tabCounts(campaigns) {
  const counts = { all: campaigns.length, running: 0, paused: 0, draft: 0, completed: 0 };
  campaigns.forEach((c) => {
    if (c.status === 'running') counts.running += 1;
    else if (c.status === 'paused' || c.status === 'pausing') counts.paused += 1;
    else if (c.status === 'draft') counts.draft += 1;
    else if (c.status === 'completed') counts.completed += 1;
  });
  return counts;
}

export function campaignsToCsv(campaigns) {
  const header = [
    'Name',
    'Status',
    'Total Leads',
    'Completed',
    'Failed',
    'Credits Used',
    'Budget',
    'Created',
  ];
  const rows = campaigns.map((c) => [
    c.name,
    c.status,
    c.totalLeads,
    c.completedLeads,
    c.failedLeads,
    c.creditsUsed,
    c.budgetCredits,
    c.createdAt || '',
  ]);
  return [header, ...rows]
    .map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
}
