import React from 'react';

const MetricCard = ({ label, value, icon, iconClass = 'icon-blue', footer, progress }) => {
  return (
    <div className="cl-card animate-fade-in" style={{ padding: 24, minHeight: 168, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
        <span className="cl-caption" style={{ color: '#4B6358', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{label}</span>
        <div
          className={`cl-kpi-card__icon ${iconClass}`}
        >
          <span className="material-symbols-outlined">{icon}</span>
        </div>
      </div>

      <div className="cl-metric-value" style={{ marginBottom: footer || progress ? 16 : 0 }}>{value}</div>

      {progress !== undefined && (
        <div style={{ marginTop: 'auto', marginBottom: 8 }}>
          <div style={{ width: '100%', height: 6, background: '#D1FAE5', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(Math.max(progress, 0), 100)}%`, height: '100%', background: '#047857', borderRadius: 999 }} />
          </div>
        </div>
      )}

      {footer && (
        <div className="cl-caption" style={{ marginTop: 'auto', color: '#7A9388' }}>
          {footer}
        </div>
      )}
    </div>
  );
};

export default MetricCard;
