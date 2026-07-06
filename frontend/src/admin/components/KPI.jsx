import React from 'react';

export default function KPI({
  title,
  value,
  icon,
  change = null,
  trend = 'up',
  footer = null,
  className = ''
}) {
  return (
    <div className={`kpi-card ${className}`}>
      {/* Top row: label + icon */}
      <div className="kpi-card__header">
        <span className="kpi-card__label">{title}</span>
        {icon && (
          <span className="material-symbols-outlined kpi-card__icon">{icon}</span>
        )}
      </div>

      {/* Value + trend */}
      <div className="kpi-card__value-row">
        <span className="kpi-card__value tabular-nums">{value}</span>
        {change && (
          <span className={`kpi-card__trend ${trend === 'up' ? 'kpi-card__trend--up' : 'kpi-card__trend--down'}`}>
            <span className="material-symbols-outlined kpi-card__trend-icon">
              {trend === 'up' ? 'trending_up' : 'trending_down'}
            </span>
            {change}
          </span>
        )}
      </div>

      {/* Footer slot */}
      {footer && (
        <div className="kpi-card__footer">
          {footer}
        </div>
      )}
    </div>
  );
}
