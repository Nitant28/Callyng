import './CampaignAnalyticsRow.css';

const fmt = (n) => (n ?? 0).toLocaleString('en-IN');

const METRICS = [
  { key: 'total_leads', label: 'Total Leads' },
  { key: 'interested_leads', label: 'Interested' },
  { key: 'not_interested_leads', label: 'Not Interested' },
  { key: 'answered_leads', label: 'Answered' },
  { key: 'busy_leads', label: 'Busy' },
  { key: 'pending_leads', label: 'Pending' },
  { key: 'calling_leads', label: 'On Call' },
  { key: 'failed_leads', label: 'Failed' },
  { key: 'callback_leads', label: 'Callback' },
];

const CampaignAnalyticsRow = ({ campaign, loading }) => {
  if (loading) {
    return (
      <div className="cw-analytics cw-analytics--loading">
        {METRICS.map(({ key }) => (
          <div key={key} className="cw-analytics__cell ds-shimmer" />
        ))}
      </div>
    );
  }

  return (
    <section className="cw-analytics" aria-label="Campaign analytics">
      {METRICS.map(({ key, label }) => (
        <div key={key} className="cw-analytics__cell">
          <span className="cw-analytics__label">{label}</span>
          <span className="cw-analytics__value">{fmt(campaign?.[key])}</span>
        </div>
      ))}
    </section>
  );
};

export default CampaignAnalyticsRow;
