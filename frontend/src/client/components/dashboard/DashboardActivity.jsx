import { formatCallCost } from '../../../utils/callLogsHelpers';

const STATUS_STYLES = {
  live:    { bg: '#EFF6FF', color: '#2563EB', label: 'Live' },
  success: { bg: '#ECFDF5', color: '#16A34A', label: 'Interested' },
  info:    { bg: '#F5F3FF', color: '#7C3AED', label: 'Answered' },
  warning: { bg: '#FFF7ED', color: '#EA580C', label: 'No answer' },
  danger:  { bg: '#FEF2F2', color: '#DC2626', label: 'Failed' },
  muted:   { bg: '#F8FAFC', color: '#64748B', label: 'Not interested' },
  neutral: { bg: '#F8FAFC', color: '#64748B', label: 'Completed' },
};

const formatDuration = (seconds) => {
  if (!seconds || !Number.isFinite(seconds)) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
};

const StatusPill = ({ tone, title }) => {
  const style = STATUS_STYLES[tone] || STATUS_STYLES.neutral;
  return (
    <span
      className="cl-activity-pill"
      style={{ background: style.bg, color: style.color }}
    >
      {title || style.label}
    </span>
  );
};

const DashboardActivity = ({ activityEvents, liveCalls = 0 }) => {
  const items = activityEvents.slice(0, 25);
  const hasLive = liveCalls > 0 || items.some((e) => e.isLive);

  return (
    <div className="cl-card cl-dashboard-activity">
      <div className="cl-dashboard-activity__header">
        <div>
          <h2 className="cl-card-title">Live Activity</h2>
          <p className="cl-dashboard-activity__subtitle">
            {hasLive ? 'Real-time call status' : 'Most recent calls'}
          </p>
        </div>
        {hasLive && (
          <span className="cl-activity-live-badge">
            <span className="cl-activity-live-badge__dot" />
            {liveCalls || items.filter((e) => e.isLive).length} live
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <div className="cl-dashboard-activity__empty">
          <span className="material-symbols-outlined">history</span>
          <p>No calls yet</p>
          <span>Activity will appear when campaigns start dialing</span>
        </div>
      ) : (
        <div className="cl-activity-table">
          <div className="cl-activity-table__head">
            <span>Time</span>
            <span>Lead</span>
            <span>Status</span>
            <span>Duration</span>
            <span>Cost</span>
          </div>
          <div className="cl-activity-table__body">
            {items.map((event) => (
              <div
                key={event.id}
                className={`cl-activity-table__row${event.isLive ? ' cl-activity-table__row--live' : ''}`}
              >
                <span className="cl-activity-table__time">
                  {event.isLive ? (
                    <span className="cl-activity-table__live-label">Live</span>
                  ) : (
                    event.clock || event.time
                  )}
                </span>
                <div className="cl-activity-table__lead">
                  <strong>{event.leadName}</strong>
                  <span>{event.campaignName}</span>
                  {event.leadPhone && <span className="cl-activity-table__phone">{event.leadPhone}</span>}
                </div>
                <div className="cl-activity-table__status">
                  <StatusPill tone={event.tone} title={event.title} />
                </div>
                <span className="cl-activity-table__duration">
                  {event.duration != null ? formatDuration(event.duration) : '—'}
                </span>
                <span className="cl-activity-table__cost">
                  {formatCallCost(event.creditsUsed, { inProgress: event.isLive })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardActivity;
