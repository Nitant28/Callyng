import { useMemo } from 'react';
import './Dashboard.css';

const formatRelativeTime = (iso) => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

const getInitials = (name) => {
  if (!name) return '?';
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
};

const ActivitySkeleton = () => (
  <>
    {[1, 2, 3, 4, 5].map((i) => (
      <div key={i} className="activity-item activity-item--skeleton">
        <div className="activity-item__avatar ds-shimmer" />
        <div className="activity-item__info">
          <div className="activity-item__skeleton-line ds-shimmer" />
          <div className="activity-item__skeleton-line activity-item__skeleton-line--short ds-shimmer" />
        </div>
      </div>
    ))}
  </>
);

const ActivityCard = ({ calls = [], campaigns = [], loading, error }) => {
  const campaignById = useMemo(() => {
    const map = {};
    campaigns.forEach((c) => {
      if (c?.id) map[c.id] = c.title;
    });
    return map;
  }, [campaigns]);

  return (
    <div className="activity-panel ds-enter ds-enter-7">
      <div className="activity-panel__header">
        <h2 className="activity-panel__title">Recent Activity</h2>
      </div>

      {error && <p className="activity-panel__error">{error}</p>}

      <div className="activity-panel__list">
        {loading && <ActivitySkeleton />}

        {!loading && !error && calls.length === 0 && (
          <p className="activity-panel__empty">No recent calls.</p>
        )}

        {!loading &&
          calls.map((call) => {
            const campaignName = call.campaignId
              ? campaignById[call.campaignId] ?? 'Campaign'
              : 'Campaign';

            return (
              <div key={call.sessionCallId} className="activity-item ds-content-loaded">
                <div className="activity-item__avatar">{getInitials(call.leadName)}</div>
                <div className="activity-item__info">
                  <p className="activity-item__name">{call.leadName}</p>
                  <p className="activity-item__outcome">
                    {call.outcome ?? 'Call logged'}
                  </p>
                  <p className="activity-item__campaign">{campaignName}</p>
                </div>
                <span className="activity-item__time">{formatRelativeTime(call.createdAt)}</span>
              </div>
            );
          })}
      </div>
    </div>
  );
};

export default ActivityCard;
