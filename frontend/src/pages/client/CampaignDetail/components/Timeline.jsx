import './Timeline.css';

const fmtDate = (iso) => {
  if (!iso) return null;
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const buildEvents = (campaign) => {
  const events = [];
  if (campaign.created_at) {
    events.push({ label: 'Campaign Created', at: campaign.created_at, done: true });
  }
  if ((campaign.total_leads || 0) > 0) {
    events.push({
      label: 'Leads Imported',
      detail: `${campaign.total_leads} leads`,
      done: true,
    });
  }
  if (['running', 'pausing', 'paused', 'completed'].includes(campaign.status)) {
    events.push({ label: 'Campaign Started', done: true });
  }
  if ((campaign.callback_leads || 0) > 0) {
    events.push({
      label: 'Callbacks Scheduled',
      detail: `${campaign.callback_leads} leads`,
      done: true,
    });
  }
  if (campaign.status === 'completed') {
    events.push({ label: 'Campaign Completed', done: true });
  } else if (campaign.status === 'cancelled') {
    events.push({ label: 'Campaign Cancelled', done: true });
  } else {
    events.push({ label: 'Campaign Completed', done: false });
  }
  return events;
};

const Timeline = ({ campaign }) => {
  const events = buildEvents(campaign);

  return (
    <section className="cdet-timeline">
      <h3>Campaign Timeline</h3>
      <ol className="cdet-timeline__list">
        {events.map((ev, i) => (
          <li key={i} className={ev.done ? 'cdet-timeline__item--done' : 'cdet-timeline__item--pending'}>
            <span className="cdet-timeline__dot" />
            <div>
              <span className="cdet-timeline__label">{ev.label}</span>
              {ev.detail && <span className="cdet-timeline__detail">{ev.detail}</span>}
              {ev.at && <span className="cdet-timeline__time">{fmtDate(ev.at)}</span>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
};

export default Timeline;
