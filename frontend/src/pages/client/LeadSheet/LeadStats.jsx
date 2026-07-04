const METRICS = [
  { key: 'uploaded', label: 'Uploaded' },
  { key: 'interested', label: 'Interested' },
  { key: 'pending', label: 'Pending' },
  { key: 'callback', label: 'Callback' },
  { key: 'completed', label: 'Completed' },
  { key: 'failed', label: 'Failed' },
];

const fmt = (n) => (n ?? 0).toLocaleString('en-IN');

const LeadStats = ({ stats, loading }) => (
  <section className="lead-sheet__stats" aria-label="Lead metrics">
    {METRICS.map(({ key, label }) => (
      <div key={key} className="lead-sheet__stat">
        <span>{label}</span>
        <strong>{loading ? '—' : fmt(stats?.[key])}</strong>
      </div>
    ))}
  </section>
);

export default LeadStats;
