import {
  countActiveCampaigns,
  sumInterestedLeadsIfPresent,
} from './dashboardCalculations';

const sum = (campaigns, field) =>
  (campaigns ?? []).reduce((s, c) => s + (c[field] ?? 0), 0);

export function creditsRemainingPercent(balance, campaigns) {
  if (balance == null) return null;
  const budgetTotal = sum(campaigns, 'budgetCredits');
  if (budgetTotal > 0) {
    return Math.min(100, Math.round((balance / budgetTotal) * 100));
  }
  const used = sum(campaigns, 'creditsUsed');
  if (used > 0) {
    return Math.min(100, Math.round((balance / (balance + used)) * 100));
  }
  return null;
}

export function computeConversionRate(credits, campaigns) {
  if (credits?.conversionRate != null && Number.isFinite(credits.conversionRate)) {
    return credits.conversionRate;
  }
  const interested = sumInterestedLeadsIfPresent(campaigns);
  const totalLeads = sum(campaigns, 'totalLeads');
  if (interested != null && totalLeads > 0) {
    return (interested / totalLeads) * 100;
  }
  const completed = sum(campaigns, 'completedLeads');
  if (totalLeads > 0 && completed > 0) {
    return (completed / totalLeads) * 100;
  }
  return null;
}

export function computeCampaignHealth(campaign) {
  const total = campaign?.totalLeads ?? 0;
  const interested = campaign?.interestedLeads;
  if (interested != null && total > 0) {
    const pct = (interested / total) * 100;
    if (pct >= 15) return { label: 'Excellent', tone: 'green', pct };
    if (pct >= 5) return { label: 'Stable', tone: 'orange', pct };
    return { label: 'Needs attention', tone: 'red', pct };
  }
  if (campaign?.status === 'failed') return { label: 'Needs attention', tone: 'red', pct: null };
  if (campaign?.status === 'running') return { label: 'Stable', tone: 'green', pct: null };
  if (campaign?.status === 'completed') return { label: 'Excellent', tone: 'blue', pct: null };
  return { label: '—', tone: 'neutral', pct: null };
}

export function computePortfolioHealth(campaigns) {
  if (!campaigns?.length) return null;
  const scores = campaigns
    .filter((c) => (c.totalLeads ?? 0) > 0)
    .map((c) => {
      if (c.interestedLeads != null) return (c.interestedLeads / c.totalLeads) * 100;
      return ((c.completedLeads ?? 0) / c.totalLeads) * 100;
    });
  if (!scores.length) return null;
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
}

export function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

export function formatLastSync(iso) {
  if (!iso) return '—';
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 5) return 'just now';
  if (sec < 60) return `${sec} sec ago`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} hr ago`;
}

export function formatRelUpdated(iso) {
  if (!iso) return null;
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'Updated just now';
  if (m === 1) return 'Updated 1 min ago';
  if (m < 60) return `Updated ${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `Updated ${h} hr ago`;
  return `Updated ${Math.floor(h / 24)}d ago`;
}

const classifyOutcome = (outcome) => {
  const o = (outcome || '').toLowerCase();
  if (o.includes('interest')) return 'interested';
  if (o.includes('fail') || o.includes('carrier')) return 'failed';
  if (o.includes('voicemail') || o.includes('no answer')) return 'unanswered';
  if (o.includes('complete') || o.includes('answer')) return 'answered';
  return 'other';
};

export function buildExecutiveSummary(calls, campaigns) {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayCalls = (calls ?? []).filter(
    (c) => c.createdAt && new Date(c.createdAt) >= todayStart,
  );

  const summary = {
    attempted: 0,
    answered: 0,
    interested: 0,
    converted: 0,
    failed: 0,
    source: 'campaigns',
    label: 'Campaign totals',
  };

  if (todayCalls.length > 0) {
    summary.source = 'calls_today';
    summary.label = "Today's summary";
    todayCalls.forEach((c) => {
      summary.attempted += 1;
      const kind = classifyOutcome(c.outcome);
      if (kind === 'interested') {
        summary.interested += 1;
        summary.answered += 1;
        summary.converted += 1;
      } else if (kind === 'failed') summary.failed += 1;
      else if (kind === 'answered') summary.answered += 1;
    });
    return summary;
  }

  summary.attempted =
    sum(campaigns, 'completedLeads') +
    sum(campaigns, 'callingLeads') +
    sum(campaigns, 'failedLeads') +
    sum(campaigns, 'pendingLeads');
  summary.failed = sum(campaigns, 'failedLeads');
  summary.answered = sum(campaigns, 'completedLeads');
  const interested = sumInterestedLeadsIfPresent(campaigns);
  if (interested != null) {
    summary.interested = interested;
    summary.converted = interested;
  } else {
    summary.interested = sum(campaigns, 'completedLeads');
    summary.converted = summary.interested;
  }
  return summary;
}

export function computeCallStats(calls) {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayCalls = (calls ?? []).filter(
    (c) => c.createdAt && new Date(c.createdAt) >= todayStart,
  );

  const durations = todayCalls
    .map((c) => c.durationSeconds)
    .filter((d) => d != null && d > 0);
  const avgDurationSec = durations.length
    ? durations.reduce((a, b) => a + b, 0) / durations.length
    : null;

  const hourBuckets = {};
  todayCalls.forEach((c) => {
    const h = new Date(c.createdAt).getHours();
    hourBuckets[h] = (hourBuckets[h] || 0) + 1;
  });
  const peakToday = Object.values(hourBuckets).length
    ? Math.max(...Object.values(hourBuckets))
    : null;

  const answered = todayCalls.filter((c) => {
    const k = classifyOutcome(c.outcome);
    return k === 'answered' || k === 'interested';
  }).length;
  const answerRate = todayCalls.length > 0 ? (answered / todayCalls.length) * 100 : null;

  return { avgDurationSec, peakToday, answerRate, todayCount: todayCalls.length };
}

export function buildDashboardKpis(credits, campaigns, calls = []) {
  const balance = credits?.balanceCredits ?? null;
  const maxConcurrent = credits?.maxConcurrentCalls ?? null;
  const running = countActiveCampaigns(campaigns);
  const totalCampaigns = campaigns?.length ?? 0;
  const totalLeads = sum(campaigns, 'totalLeads');
  const calling = sum(campaigns, 'callingLeads');
  const interested = sumInterestedLeadsIfPresent(campaigns);
  const conversionRate = computeConversionRate(credits, campaigns);
  const remainingPct = creditsRemainingPercent(balance, campaigns);
  const activeCampaignPct = totalCampaigns > 0 ? Math.round((running / totalCampaigns) * 100) : 0;
  const concurrentPct = maxConcurrent > 0 ? Math.round((calling / maxConcurrent) * 100) : null;
  const callStats = computeCallStats(calls);

  const resetDate = new Date();
  resetDate.setMonth(resetDate.getMonth() + 1, 1);
  const resetLabel = resetDate.toLocaleDateString('en-US', { day: 'numeric', month: 'long' });

  return {
    credits: {
      value: balance,
      remainingPct,
      subtitle: remainingPct != null ? `${remainingPct}% remaining` : 'Available balance',
      footer: balance != null ? `Available until ${resetLabel}` : null,
    },
    campaigns: {
      running,
      total: totalCampaigns,
      activePct: activeCampaignPct,
      subtitle: totalCampaigns > 0 ? `${totalCampaigns} total` : 'No campaigns',
    },
    leads: {
      qualified: interested,
      total: totalLeads,
      subtitle:
        interested != null
          ? `${totalLeads} total leads`
          : totalLeads > 0
            ? `${totalLeads} leads across campaigns`
            : 'No leads yet',
      hasQualifiedField: interested != null,
    },
    concurrent: {
      live: calling,
      max: maxConcurrent,
      pct: concurrentPct,
      peakToday: callStats.peakToday,
      avgDuration: formatDuration(callStats.avgDurationSec),
      subtitle:
        maxConcurrent != null
          ? `${calling} of ${maxConcurrent} slots`
          : calling > 0
            ? 'Live now'
            : 'No live calls',
      isLive: calling > 0,
    },
    conversion: {
      rate: conversionRate,
      subtitle:
        conversionRate != null
          ? credits?.conversionRate != null
            ? 'From account metrics'
            : interested != null
              ? 'Interested / total leads'
              : 'Completed / total leads'
          : 'Awaiting completed calls',
    },
    executive: {
      answerRate: callStats.answerRate,
      avgDuration: formatDuration(callStats.avgDurationSec),
      costPerLead: credits?.costPerLead ?? null,
      healthScore: computePortfolioHealth(campaigns),
    },
  };
}

export function systemStatusMessage(error, campaigns) {
  const hasError = error?.credits || error?.campaigns || error?.calls;
  const failed = sum(campaigns, 'failedLeads');
  const calling = sum(campaigns, 'callingLeads');
  if (hasError) return 'Some services need attention';
  if (failed > 0 && calling === 0) return 'Review failed leads in campaigns';
  return 'Everything looks healthy today';
}
