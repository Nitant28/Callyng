import React from 'react';

/**
 * LeadAnalyticsRow displays a set of key lead statistics in a single horizontal row.
 * It uses the existing `renderKpiCard` style from CampaignDetail for visual consistency.
 * Props:
 *   - campaign: campaign object containing statistic fields.
 *   - total: total number of leads for percentage calculations.
 */
const LeadAnalyticsRow = ({ campaign, total }) => {
  const cards = [
    { title: 'Total Leads', value: (campaign.total_leads || 0).toLocaleString() },
    { title: 'Interested', value: (campaign.interested_leads || 0).toLocaleString(), pct: total > 0 ? ((campaign.interested_leads || 0) / total) * 100 : 0 },
    { title: 'Not Interested', value: (campaign.not_interested_leads || 0).toLocaleString(), pct: total > 0 ? ((campaign.not_interested_leads || 0) / total) * 100 : 0 },
    { title: 'Answered', value: (campaign.answered_leads || 0).toLocaleString(), pct: total > 0 ? ((campaign.answered_leads || 0) / total) * 100 : 0 },
    { title: 'Not Answered', value: (campaign.not_answered_leads || 0).toLocaleString(), pct: total > 0 ? ((campaign.not_answered_leads || 0) / total) * 100 : 0 }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
      {cards.map((c) => (
        <div key={c.title} className="cl-card flex flex-col p-4">
          <h4 className="text-sm font-medium text-muted mb-1">{c.title}</h4>
          <div className="text-lg font-semibold text-primary">{c.value}</div>
          {c.pct !== undefined && (
            <div className="text-xs text-muted">{c.pct.toFixed(1)}% of total</div>
          )}
        </div>
      ))}
    </div>
  );
};

export default LeadAnalyticsRow;
