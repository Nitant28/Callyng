import './CampaignStatsGrid.css';

const fmt = (n) => (n ?? 0).toLocaleString('en-IN');

/** Campaign-level funnel KPIs only — row-level dial state lives on each lead. */
const METRICS = [
  { key: 'total_leads', label: 'Total Leads' },
  { key: 'interested_leads', label: 'Interested' },
  { key: 'not_interested_leads', label: 'Not Interested' },
  { key: 'completed_leads', label: 'Completed' },
  { key: 'busy_leads', label: 'Busy' },
  { key: 'pending_leads', label: 'Pending' },
  { key: 'calling_leads', label: 'On Call' },
  { key: 'failed_leads', label: 'Failed' },
  { key: 'callback_leads', label: 'Callback' },
];

const CampaignStatsGrid = ({ campaign }) => (
  <section className="cdet-stats" aria-label="Campaign summary">
    {METRICS.map(({ key, label }) => (
      <div key={key} className="cdet-stats__cell">
        <span className="cdet-stats__label">{label}</span>
        <span className="cdet-stats__value">{fmt(campaign?.[key])}</span>
      </div>
    ))}
  </section>
);

export default CampaignStatsGrid;
