import './SummaryStrip.css';

const fmt = (n) => (n ?? 0).toLocaleString('en-IN');

const SummaryStrip = ({ campaign }) => {
  const total = campaign.total_leads || 0;
  const attempted =
    (campaign.pending_leads || 0) +
    (campaign.calling_leads || 0) +
    (campaign.callback_leads || 0) +
    (campaign.completed_leads || 0) +
    (campaign.failed_leads || 0);
  const connected = campaign.completed_leads || 0;

  const rows = [
    [
      { label: 'Attempted', value: fmt(attempted || total) },
      { label: 'Connected', value: fmt(connected) },
    ],
    [
      { label: 'Completed', value: fmt(campaign.completed_leads) },
      { label: 'Failed', value: fmt(campaign.failed_leads) },
    ],
    [{ label: 'Callback Scheduled', value: fmt(campaign.callback_leads), full: true }],
  ];

  return (
    <section className="cdet-summary">
      {rows.map((row, i) => (
        <div key={i} className={`cdet-summary__row ${row.some((c) => c.full) ? 'cdet-summary__row--full' : ''}`}>
          {row.map((cell) => (
            <div key={cell.label} className={`cdet-summary__cell ${cell.full ? 'cdet-summary__cell--full' : ''}`}>
              <span className="cdet-summary__label">{cell.label}</span>
              <span className="cdet-summary__value">{cell.value}</span>
            </div>
          ))}
        </div>
      ))}
    </section>
  );
};

export default SummaryStrip;
