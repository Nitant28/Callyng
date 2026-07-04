import { useMemo, useState } from 'react';
import { buildActivityEvents } from '../../../utils/activityEvents';
import { ACTIVITY_RANGES, isInRange } from '../../../utils/dateRangeHelpers';
import './LiveActivityFeed.css';

const LiveActivityFeed = ({ calls = [], campaigns = [], loading, error }) => {
  const [range, setRange] = useState('today');

  const events = useMemo(() => {
    const all = buildActivityEvents(calls, campaigns);
    return all.filter((e) => isInRange(e.time, range));
  }, [calls, campaigns, range]);

  return (
    <section className="cd-activity">
      <div className="cd-activity__header">
        <h2 className="cd-activity__title">Live Activity</h2>
        <select
          className="cd-activity__select"
          value={range}
          onChange={(e) => setRange(e.target.value)}
          aria-label="Activity date range"
        >
          {ACTIVITY_RANGES.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
      </div>

      {error && <p className="cd-activity__error">{error}</p>}

      <div className="cd-activity__cols">
        <span>Time</span>
        <span>Campaign</span>
        <span>Lead</span>
        <span>Status</span>
        <span>Duration</span>
      </div>

      <div className="cd-activity__timeline">
        {loading && [1, 2, 3, 4].map((i) => (
          <div key={i} className="cd-activity__row cd-activity__row--skel">
            <div className="ds-shimmer" style={{ height: 16, width: '100%' }} />
          </div>
        ))}
        {!loading && !error && events.length === 0 && (
          <div className="cd-activity__empty">
            <p>No activity in this period</p>
          </div>
        )}
        {!loading && events.map((event) => (
          <div key={event.id} className="cd-activity__row">
            <span className="cd-activity__cell cd-activity__cell--time">{event.clock}</span>
            <span className="cd-activity__cell">{event.campaign}</span>
            <span className="cd-activity__cell">{event.leadName}</span>
            <span className="cd-activity__cell cd-activity__cell--status">{event.status}</span>
            <span className="cd-activity__cell cd-activity__cell--muted">{event.duration || '—'}</span>
          </div>
        ))}
      </div>
    </section>
  );
};

export default LiveActivityFeed;
