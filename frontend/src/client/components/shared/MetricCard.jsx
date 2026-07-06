import React from 'react';

const MetricCard = ({ label, value, icon, iconClass = 'icon-blue', footer, progress }) => {
  return (
    <div className="cl-card animate-fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <span className="cl-caption" style={{ color: '#64748B', fontWeight: 600 }}>{label}</span>
        <div 
          className={`cl-kpi-card__icon ${iconClass}`} 
          style={{ 
            width: '32px', 
            height: '32px', 
            borderRadius: '6px', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            flexShrink: 0
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>{icon}</span>
        </div>
      </div>
      
      <div className="cl-metric-value" style={{ marginBottom: footer || progress ? '16px' : '0' }}>{value}</div>
      
      {progress !== undefined && (
        <div style={{ marginTop: 'auto', marginBottom: '8px' }}>
          <div style={{ width: '100%', height: '4px', background: '#E2E8F0', borderRadius: '2px', overflow: 'hidden', marginBottom: '6px' }}>
            <div style={{ width: `${Math.min(Math.max(progress, 0), 100)}%`, height: '100%', background: 'var(--blue)', borderRadius: '2px' }} />
          </div>
        </div>
      )}
      
      {footer && (
        <div className="cl-caption" style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#64748B' }}>
          {footer}
        </div>
      )}
    </div>
  );
};

export default MetricCard;
