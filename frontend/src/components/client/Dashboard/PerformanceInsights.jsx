import { useMemo } from 'react';
import { computePortfolioHealth, computeCallStats } from '../../../utils/dashboardKpis';
import './PerformanceInsights.css';

const healthLabel = (score) => {
  if (score == null) return { label: 'No data', tone: 'neutral' };
  if (score >= 15) return { label: 'Excellent', tone: 'green' };
  if (score >= 8) return { label: 'Good', tone: 'blue' };
  if (score >= 3) return { label: 'Fair', tone: 'orange' };
  return { label: 'Needs attention', tone: 'red' };
};

const PerformanceInsights = ({ campaigns = [], calls = [], loading, refreshLatencyMs }) => {
  const healthScore = useMemo(() => computePortfolioHealth(campaigns), [campaigns]);
  const health = healthLabel(healthScore);
  const runningCount = campaigns.filter((c) => c.status === 'running').length;
  const callStats = useMemo(() => computeCallStats(calls), [calls]);

  const peakHint = useMemo(() => {
    if (!calls?.length) return null;
    const hours = {};
    calls.forEach((c) => {
      if (!c.createdAt) return;
      const h = new Date(c.createdAt).getHours();
      hours[h] = (hours[h] || 0) + 1;
    });
    const top = Object.entries(hours).sort((a, b) => b[1] - a[1])[0];
    if (!top) return null;
    const h = Number(top[0]);
    const end = (h + 2) % 24;
    const fmt = (hr) => `${hr % 12 || 12}${hr >= 12 ? 'PM' : 'AM'}`;
    return `${fmt(h)}–${fmt(end)}`;
  }, [calls]);

  if (loading) {
    return (
      <section className="cd-insights cd-insights--skeleton ds-skeleton">
        <div className="ds-shimmer" style={{ height: 20, width: '70%', marginBottom: 12 }} />
        {[1, 2, 3].map((i) => (
          <div key={i} className="ds-shimmer" style={{ height: 48, marginBottom: 8 }} />
        ))}
      </section>
    );
  }

  const ringPct = healthScore ?? 0;

  return (
    <section className="cd-insights">
      <h2 className="cd-insights__title">AI Operations</h2>

      <div className="cd-insights__block">
        <div className="cd-insights__block-head">
          <span>Health</span>
          <span className={`cd-insights__health cd-insights__health--${health.tone}`}>
            {healthScore != null ? `${healthScore}%` : '—'} · {health.label}
          </span>
        </div>
        <div className="cd-insights__bar">
          <div
            className={`cd-insights__bar-fill cd-insights__bar-fill--${health.tone}`}
            style={{ width: `${Math.min(100, ringPct)}%` }}
          />
        </div>
      </div>

      <div className="cd-insights__divider" />

      <div className="cd-insights__row">
        <div>
          <p className="cd-insights__label">Voice latency</p>
          <p className="cd-insights__value">{refreshLatencyMs != null ? `${refreshLatencyMs} ms` : '—'}</p>
        </div>
      </div>

      <div className="cd-insights__divider" />

      <div className="cd-insights__row">
        <div>
          <p className="cd-insights__label">Average talk time</p>
          <p className="cd-insights__value">
            {callStats.avgDurationSec != null
              ? `${Math.floor(callStats.avgDurationSec / 60)}m ${String(Math.round(callStats.avgDurationSec % 60)).padStart(2, '0')}s`
              : '—'}
          </p>
        </div>
      </div>

      <div className="cd-insights__divider" />

      <div className="cd-insights__row">
        <div>
          <p className="cd-insights__label">Peak hour</p>
          <p className="cd-insights__value">{peakHint ?? '10 AM – 1 PM'}</p>
        </div>
        <span className="cd-insights__side">{runningCount} active</span>
      </div>

      <div className="cd-insights__divider" />

      <div className="cd-insights__block">
        <p className="cd-insights__label">Recommendation</p>
        <p className="cd-insights__value">
          {runningCount > 0 ? 'Increase concurrency by 1–2' : 'Start a campaign to collect signals'}
        </p>
        <p className="cd-insights__hint">
          {runningCount > 0
            ? 'Scale during peak window if credits allow.'
            : 'Operations insights improve with live call data.'}
        </p>
      </div>

      <div className="cd-insights__confidence">
        <svg className="cd-insights__ring" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r="28" fill="none" stroke="#e8edf6" strokeWidth="5" />
          <circle
            cx="32"
            cy="32"
            r="28"
            fill="none"
            stroke="#2563eb"
            strokeWidth="5"
            strokeDasharray={`${ringPct * 1.76} 176`}
            strokeLinecap="round"
            transform="rotate(-90 32 32)"
          />
          <text x="32" y="36" textAnchor="middle" className="cd-insights__ring-text">
            {healthScore ?? '—'}
          </text>
        </svg>
        <div>
          <p className="cd-insights__label">Confidence</p>
          <p className="cd-insights__hint">Derived from campaign outcomes</p>
        </div>
      </div>
    </section>
  );
};

export default PerformanceInsights;
