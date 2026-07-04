import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './RecentActivity.css';

const clockTime = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return '';
  }
};

const relTime = (iso) => {
  if (!iso) return '';
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
};

const eventMeta = (call) => {
  if (call.inProgress) {
    return {
      icon: 'ring_volume',
      tone: 'live',
      title: `Calling ${call.leadName}`,
      sub: 'On call now',
    };
  }

  const o = (call.outcome || '').toString();
  if (o === 'No_Answer' || o === 'Busy') {
    return { icon: 'phone_missed', tone: 'warning', title: 'Unanswered', sub: call.leadName };
  }
  if (o.includes('Interest') && o !== 'Not_Interested') {
    return { icon: 'check_circle', tone: 'success', title: 'Lead Interested', sub: call.leadName };
  }
  if (o === 'Not_Interested') {
    return { icon: 'call_end', tone: 'neutral', title: 'Answered · Not interested', sub: call.leadName };
  }
  if (o === 'Callback_Requested') {
    return { icon: 'schedule', tone: 'warning', title: 'Callback scheduled', sub: call.leadName };
  }
  if (o.includes('fail') || o.includes('Carrier')) {
    return { icon: 'warning', tone: 'danger', title: call.outcome ?? 'Carrier Failed', sub: call.leadName };
  }
  if (o) {
    return { icon: 'call', tone: 'blue', title: o.replace(/_/g, ' '), sub: call.leadName };
  }
  return { icon: 'call', tone: 'blue', title: 'Call logged', sub: call.leadName };
};

const sortCallsForActivity = (calls) => {
  const live = [];
  const rest = [];
  calls.forEach((c) => {
    if (c.inProgress) live.push(c);
    else rest.push(c);
  });
  return [...live, ...rest];
};

const RecentActivity = ({ calls = [], campaigns = [], loading, error }) => {
  const navigate = useNavigate();
  const campaignMap = useMemo(() => {
    const m = {};
    campaigns.forEach((c) => { if (c?.id) m[c.id] = c.title; });
    return m;
  }, [campaigns]);

  const orderedCalls = useMemo(() => sortCallsForActivity(calls), [calls]);

  return (
    <section className="cd-activity">
      <div className="cd-activity__header">
        <h2>Recent Activity</h2>
        <button type="button" className="cd-activity__action" onClick={() => navigate('/app/calls')}>
          View all
        </button>
      </div>
      {error && <p className="cd-activity__error">{error}</p>}
      <div className="cd-activity__timeline">
        {loading && [1, 2, 3, 4].map((i) => (
          <div key={i} className="cd-activity__item cd-activity__item--skel">
            <div className="ds-shimmer" style={{ width: 32, height: 32, borderRadius: 10 }} />
            <div className="ds-shimmer" style={{ flex: 1, height: 40 }} />
          </div>
        ))}
        {!loading && !error && orderedCalls.length === 0 && (
          <div className="ds-empty">
            <span className="material-symbols-outlined ds-empty__icon">history</span>
            <p className="ds-empty__title">No recent activity</p>
            <p className="ds-empty__desc">Live call outcomes will stream here as campaigns run.</p>
          </div>
        )}
        {!loading && orderedCalls.map((call, idx) => {
          const campaign = call.campaignId ? campaignMap[call.campaignId] ?? 'Campaign' : 'Campaign';
          const meta = eventMeta(call);
          const timeIso = call.startedAt || call.createdAt;
          return (
            <div
              key={call.sessionCallId}
              className={`cd-activity__item ${call.inProgress ? 'cd-activity__item--live' : ''}`}
            >
              <div className="cd-activity__rail">
                <span className={`cd-activity__dot cd-activity__dot--${meta.tone}`}>
                  <span className="material-symbols-outlined">{meta.icon}</span>
                </span>
                {idx < orderedCalls.length - 1 && <span className="cd-activity__line" />}
              </div>
              <div className="cd-activity__content">
                <p className="cd-activity__title">{meta.title}</p>
                <p className="cd-activity__sub">{meta.sub} · {campaign}</p>
                <span className="cd-activity__time">{clockTime(timeIso)} · {relTime(timeIso)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default RecentActivity;
