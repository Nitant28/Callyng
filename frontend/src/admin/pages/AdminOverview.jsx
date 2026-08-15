import React, { useState, useEffect, useCallback } from 'react';
import adminApi from '../../shared/api/admin';
import KPI from '../components/KPI';
import PageHeader from '../components/PageHeader';

/* ── Smooth animated counter ── */
const AnimatedCounter = ({ targetValue, prefix = '', decimals = 0 }) => {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (targetValue === undefined || targetValue === null) return;
    const duration = 1200;
    const fps = 60;
    const total = Math.round(duration / (1000 / fps));
    let frame = 0;
    const ease = (t) => t * (2 - t);
    const run = () => {
      frame++;
      const progress = ease(Math.min(frame / total, 1));
      setValue(targetValue * progress);
      if (frame < total) requestAnimationFrame(run);
      else setValue(targetValue);
    };
    requestAnimationFrame(run);
  }, [targetValue]);

  const formatted = decimals > 0
    ? value.toFixed(decimals)
    : Math.round(value).toLocaleString();

  return <>{prefix}{formatted}</>;
};

/* ── Status badge ── */
const StatusBadge = ({ ok }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: '5px',
    padding: '3px 10px', borderRadius: '20px',
    background: ok ? 'var(--admin-success-bg)' : 'var(--admin-error-bg)',
    color: ok ? 'var(--admin-success)' : 'var(--admin-error)',
    fontSize: 'var(--admin-text-sm)', fontWeight: 600,
  }}>
    <span style={{
      width: '6px', height: '6px', borderRadius: '50%',
      background: ok ? 'var(--admin-success)' : 'var(--admin-error)',
      display: 'inline-block',
    }} />
    {ok ? 'All Systems Nominal' : 'Degraded'}
  </span>
);

const iconStyle = (type) => {
  const map = {
    login: 'primary', api: 'success', client: 'warning', campaign: 'primary',
    call: 'primary', error: 'error',
  };
  return map[type] || 'primary';
};

export default function AdminOverview() {
  const [stats, setStats] = useState({
    total_calls_today: 0,
    active_campaigns: 0,
    credits_burned: 0,
    telephony_credits: 0,
    bot_credits: 0,
  });

  const [health, setHealth] = useState({
    status: 'unknown',
    plivo_balance: null,
    dialer_tasks: 0,
    active_calls: 0,
    pool: { size: 0, idle: 0 },
  });

  const [liveEvents, setLiveEvents] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        adminApi.get('/internal/stats'),
        adminApi.get('/internal/health'),
        adminApi.get('/internal/campaigns'),
        adminApi.get('/internal/calls', { params: { limit: 20 } }),
      ]);

      const [statsSettled, healthSettled, campaignsSettled, callsSettled] = results;
      const failures = results
        .map((r, i) => ({ r, name: ['stats', 'health', 'campaigns', 'calls'][i] }))
        .filter(({ r }) => r.status === 'rejected');

      if (failures.length === results.length) {
        const first = failures[0]?.r?.reason;
        setError(
          first?.customErrorMessage
            || first?.message
            || 'Failed to fetch dashboard stats.',
        );
        setLoading(false);
        return;
      }

      if (statsSettled.status === 'fulfilled') {
        const data = statsSettled.value.data || {};
        setStats({
          total_calls_today: data.total_calls_today || 0,
          active_campaigns: data.active_campaigns || 0,
          credits_burned: data.total_credits_used_today || 0,
          telephony_credits: data.telephony_credits_today || 0,
          bot_credits: data.bot_credits_today || 0,
        });
      }

      if (healthSettled.status === 'fulfilled') {
        const data = healthSettled.value.data || {};
        setHealth({
          status: data.status || 'unknown',
          plivo_balance: data.plivo_balance,
          dialer_tasks: data.dialer_tasks || 0,
          active_calls: data.active_calls || 0,
          pool: data.pool || { size: 0, idle: 0 },
        });
      }

      const events = [];
      const campList = campaignsSettled.status === 'fulfilled'
        ? (campaignsSettled.value.data?.campaigns || [])
        : [];
      const calls = callsSettled.status === 'fulfilled'
        ? (callsSettled.value.data?.calls || [])
        : [];

      campList.forEach((c) => {
        if (c.status === 'running') {
          events.push({
            id: `camp-${c.id}`,
            icon: 'rocket_launch',
            type: 'campaign',
            title: 'Campaign Running',
            detail: `Campaign: ${c.name}`,
            time: c.updated_at || c.created_at
              ? new Date(c.updated_at || c.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })
              : '—',
            sortAt: new Date(c.updated_at || c.created_at || 0).getTime(),
          });
        }
      });

      calls.forEach((call) => {
        events.push({
          id: `call-${call.session_call_id || call.id}`,
          icon: call.in_progress ? 'call' : 'call_end',
          type: call.in_progress ? 'call' : 'api',
          title: call.in_progress ? 'Call In Progress' : 'Call Finished',
          detail: `To: ${call.phone || call.name || 'Customer'}`,
          time: call.started_at
            ? new Date(call.started_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })
            : '—',
          sortAt: new Date(call.started_at || call.created_at || 0).getTime(),
        });
      });

      events.sort((a, b) => (b.sortAt || 0) - (a.sortAt || 0));
      setLiveEvents(events.slice(0, 12));

      if (failures.length > 0) {
        setError(
          `Partial dashboard load: failed ${failures.map((f) => f.name).join(', ')}.`,
        );
      } else {
        setError(null);
      }
    } catch (err) {
      console.error('Failed to fetch admin overview data', err);
      setError(err.customErrorMessage || err.message || 'Failed to fetch dashboard stats.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 8000);
    return () => clearInterval(id);
  }, [fetchData]);

  const plivoBalRaw = health.plivo_balance;
  const plivoBal = plivoBalRaw !== null && plivoBalRaw !== undefined
    ? `₹${(plivoBalRaw * 80.0229).toFixed(2)}`
    : 'N/A';

  const isHealthy = health.status === 'ok' || health.status === 'healthy';

  return (
    <div className="admin-page">
      <PageHeader
        title="Admin Overview"
        description="Real-time telecommunications infrastructure monitoring."
      />

      {error && (
        <div className="admin-alert admin-alert--error" style={{ marginBottom: 16 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>error</span>
          <span>{error}</span>
          <button type="button" className="btn btn-secondary" onClick={fetchData} style={{ marginLeft: 'auto', height: 32, padding: '0 12px', fontSize: 12 }}>
            Retry
          </button>
        </div>
      )}

      <div className="admin-kpi-grid">
        <KPI
          title="Total Calls Today"
          value={<AnimatedCounter targetValue={stats.total_calls_today} />}
          icon="call"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              {loading ? 'Loading…' : 'From call logs (today)'}
            </span>
          }
        />
        <KPI
          title="Active Campaigns"
          value={<AnimatedCounter targetValue={stats.active_campaigns} />}
          icon="rocket_launch"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              {health.active_calls} live call{health.active_calls === 1 ? '' : 's'}
            </span>
          }
        />
        <KPI
          title="Credits Burned"
          value={<>₹<AnimatedCounter targetValue={stats.credits_burned} decimals={2} /></>}
          icon="payments"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              Charged today from call logs
            </span>
          }
        />
        <KPI
          title="Telephony"
          value={<>₹<AnimatedCounter targetValue={stats.telephony_credits} decimals={2} /></>}
          icon="cell_tower"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              Setup / started minute (today)
            </span>
          }
        />
        <KPI
          title="Bot"
          value={<>₹<AnimatedCounter targetValue={stats.bot_credits} decimals={2} /></>}
          icon="smart_toy"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              Talk time at bot rate (today)
            </span>
          }
        />
      </div>

      <div className="admin-overview-grid">
        <div className="admin-card">
          <div className="admin-card__header-row">
            <h3 className="admin-card__title" style={{ marginBottom: 0 }}>Infrastructure Status</h3>
            <StatusBadge ok={isHealthy} />
          </div>
          <div className="admin-infra-grid">
            <div className="infra-card">
              <div className="infra-card__label">Plivo Balance</div>
              <div className="infra-card__value">{plivoBal}</div>
            </div>
            <div className="infra-card">
              <div className="infra-card__label">Dialer Tasks</div>
              <div className="infra-card__value">
                {health.dialer_tasks}
                <span className="infra-card__unit"> active</span>
              </div>
            </div>
            <div className="infra-card">
              <div className="infra-card__label">DB Pool Size</div>
              <div className="infra-card__value">
                {health.pool.size}
                <span className="infra-card__unit"> conns</span>
              </div>
            </div>
            <div className="infra-card">
              <div className="infra-card__label">DB Pool Idle</div>
              <div className="infra-card__value">
                {health.pool.idle}
                <span className="infra-card__unit"> idle</span>
              </div>
            </div>
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card__header-row">
            <h3 className="admin-card__title" style={{ marginBottom: 0 }}>Live Activity</h3>
          </div>

          <div>
            {liveEvents.length === 0 ? (
              <div className="admin-empty-inline">
                No recent campaign or call activity.
              </div>
            ) : (
              liveEvents.slice(0, 6).map((evt) => (
                <div key={evt.id} className="event-entry">
                  <div className={`event-entry__icon-wrap event-entry__icon-wrap--${iconStyle(evt.type)}`}>
                    <span className="material-symbols-outlined">{evt.icon}</span>
                  </div>
                  <div className="event-entry__body">
                    <div className="event-entry__title">{evt.title}</div>
                    <div className="event-entry__detail">{evt.detail}</div>
                  </div>
                  <div className="event-entry__time">{evt.time}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
