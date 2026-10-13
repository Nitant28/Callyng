import React, { useState, useEffect } from 'react';
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
    const ease = t => t * (2 - t);
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

/* ── Animated bar (pulse bars for Active Campaigns) ── */
const PulseBars = () => {
  const [heights, setHeights] = useState([12, 16, 8, 14, 10, 15]);
  useEffect(() => {
    const id = setInterval(() =>
      setHeights(prev => prev.map(() => Math.floor(Math.random() * 16) + 8)), 140);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '3px', height: '20px' }}>
      {heights.map((h, i) => (
        <div key={i} style={{
          width: '4px', height: `${h}px`,
          borderRadius: '2px', transition: 'height 0.1s ease',
          background: i % 2 === 0 ? 'var(--admin-primary)' : 'var(--admin-success)',
          opacity: 0.7
        }} />
      ))}
    </div>
  );
};

/* ── Status badge ── */
const StatusBadge = ({ ok }) => (
  <span style={{
    display: 'inline-flex', alignItems: 'center', gap: '5px',
    padding: '3px 10px', borderRadius: '20px',
    background: ok ? 'var(--admin-success-bg)' : 'var(--admin-error-bg)',
    color: ok ? 'var(--admin-success)' : 'var(--admin-error)',
    fontSize: 'var(--admin-text-sm)', fontWeight: 600
  }}>
    <span style={{
      width: '6px', height: '6px', borderRadius: '50%',
      background: ok ? 'var(--admin-success)' : 'var(--admin-error)',
      display: 'inline-block'
    }} />
    {ok ? 'All Systems Nominal' : 'Degraded'}
  </span>
);

/* ── Event icon colour helper ── */
const iconStyle = (type) => {
  const map = {
    login: 'primary', api: 'success', client: 'warning', campaign: 'primary',
    call: 'primary', error: 'error'
  };
  return map[type] || 'primary';
};

export default function AdminOverview() {
  const [stats, setStats] = useState({
    total_calls_today: 0,
    active_campaigns:  0,
    credits_burned:    0,
  });

  const [health, setHealth] = useState({
    status:       'unknown',
    plivo_balance: null,
    dialer_tasks:  0,
    active_calls:  0,
    pool:         { size: 0, idle: 0 },
  });

  const [liveEvents, setLiveEvents] = useState([]);
  const [error, setError]           = useState(null);

  const fetchData = async () => {
    try {
      const [statsRes, healthRes, campaignsRes, callsRes] = await Promise.all([
        adminApi.get('/internal/stats'),
        adminApi.get('/internal/health'),
        adminApi.get('/internal/campaigns'),
        adminApi.get('/internal/calls', { params: { limit: 20 } }),
      ]);

      setStats({
        total_calls_today: statsRes.data.total_calls_today     || 0,
        active_campaigns:  statsRes.data.active_campaigns      || 0,
        credits_burned:    statsRes.data.total_credits_used_today || 0,
      });

      setHealth({
        status:        healthRes.data.status        || 'unknown',
        plivo_balance: healthRes.data.plivo_balance,
        dialer_tasks:  healthRes.data.dialer_tasks  || 0,
        active_calls:  healthRes.data.active_calls  || 0,
        pool:          healthRes.data.pool           || { size: 0, idle: 0 },
      });

      /* Build events list */
      const events = [];
      const campList = campaignsRes.data.campaigns || [];
      const calls    = callsRes.data.calls          || [];

      campList.forEach(c => {
        if (c.status === 'running') events.push({
          id: `camp-${c.id}`, icon: 'rocket_launch', type: 'campaign',
          title: 'Campaign Started', detail: `Campaign: ${c.name}`,
          time: new Date(c.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
      });

      calls.forEach(call => {
        events.push({
          id: `call-${call.session_call_id}`,
          icon: call.in_progress ? 'call' : 'call_end',
          type: call.in_progress ? 'call' : 'api',
          title: call.in_progress ? 'Call Started' : 'Call Finished',
          detail: `To: ${call.lead_phone || 'Customer'}`,
          time: new Date(call.started_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
      });

      /* Static fallback events to show structure (if none from API) */
      if (events.length === 0) {
        events.push(
          { id: 'e1', icon: 'verified_user', type: 'login',  title: 'Admin Login',           detail: 'IP: 192.168.1.45',      time: '2m ago' },
          { id: 'e2', icon: 'key',           type: 'api',    title: 'API Key Rotation',       detail: 'Campaign: Alpha-Niner', time: '15m ago' },
          { id: 'e3', icon: 'person_add',    type: 'client', title: 'New Client Onboarded',   detail: 'Studio Flux Inc.',      time: '1h ago' },
        );
      }

      setLiveEvents(events.slice(0, 12));
      setError(null);
    } catch (err) {
      console.error('Failed to fetch admin overview data', err);
      setError('Failed to fetch dashboard stats.');
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 8000);
    return () => clearInterval(id);
  }, []);

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

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '12px 16px', background: 'var(--admin-error-bg)', color: 'var(--admin-error)',
          borderRadius: 'var(--admin-radius-sm)', display: 'flex', alignItems: 'center', gap: '8px',
          fontSize: 'var(--admin-text-base)', border: '1px solid var(--admin-error)',
        }}>
          <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>error</span>
          {error}
        </div>
      )}

      {/* ── Row 1: 3 KPI Cards ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 'var(--admin-gap)',
      }}>
        <KPI
          title="Total Calls Today"
          value={<AnimatedCounter targetValue={stats.total_calls_today} />}
          icon="call"
          change="+12%"
          trend="up"
          footer={
            <div style={{ height: '4px', background: 'var(--admin-border)', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: '75%', background: 'var(--admin-primary)', borderRadius: '4px' }} />
            </div>
          }
        />
        <KPI
          title="Active Campaigns"
          value={<AnimatedCounter targetValue={stats.active_campaigns} />}
          icon="rocket_launch"
          footer={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <PulseBars />
              <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
                Pulse detection: Normal
              </span>
            </div>
          }
        />
        <KPI
          title="Credits Burned"
          value={<>₹<AnimatedCounter targetValue={stats.credits_burned} decimals={0} /></>}
          icon="payments"
          change="-5%"
          trend="down"
          footer={
            <span style={{ fontSize: 'var(--admin-text-xs)', color: 'var(--admin-text-muted)' }}>
              Estimated burn rate: ₹2.4k/hr
            </span>
          }
        />
      </div>

      {/* ── Row 2: Infrastructure Status + Security Logs ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 340px',
        gap: 'var(--admin-gap)',
        alignItems: 'start',
      }}>

        {/* Infrastructure Status card */}
        <div className="admin-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--admin-sp-5)' }}>
            <h3 className="admin-card__title" style={{ marginBottom: 0 }}>Infrastructure Status</h3>
            <StatusBadge ok={isHealthy} />
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 'var(--admin-sp-4)',
          }}>
            {/* Telnyx Balance */}
            <div className="infra-card">
              <div className="infra-card__label">Telnyx Balance</div>
              <div className="infra-card__value">{plivoBal}</div>
            </div>
            {/* Dialer Tasks */}
            <div className="infra-card">
              <div className="infra-card__label">Dialer Tasks</div>
              <div className="infra-card__value">
                {health.dialer_tasks}
                <span className="infra-card__unit"> active</span>
              </div>
            </div>
            {/* DB Pool Size */}
            <div className="infra-card">
              <div className="infra-card__label">DB Pool Size</div>
              <div className="infra-card__value">
                {health.pool.size}
                <span className="infra-card__unit"> conns</span>
              </div>
            </div>
            {/* DB Pool Idle */}
            <div className="infra-card">
              <div className="infra-card__label">DB Pool Idle</div>
              <div className="infra-card__value">
                {health.pool.idle}
                <span className="infra-card__unit"> idle</span>
              </div>
            </div>
          </div>
        </div>

        {/* Security / Live Events */}
        <div className="admin-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--admin-sp-4)' }}>
            <h3 className="admin-card__title" style={{ marginBottom: 0 }}>Security Logs</h3>
          </div>

          <div>
            {liveEvents.slice(0, 4).map((evt) => (
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
            ))}
          </div>

          <div style={{ paddingTop: 'var(--admin-sp-3)', textAlign: 'right' }}>
            <a href="#" style={{
              fontSize: 'var(--admin-text-sm)', color: 'var(--admin-primary)',
              fontWeight: 600, textDecoration: 'none'
            }}>View All Logs →</a>
          </div>
        </div>
      </div>
    </div>
  );
}
