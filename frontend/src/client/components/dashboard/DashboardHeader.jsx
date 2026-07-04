import React from 'react';
import DateRangeDropdown from '../shared/DateRangeDropdown';

const DashboardHeader = ({
  clientName,
  period,
  onPeriodChange,
  customStart,
  customEnd,
  onCustomStartChange,
  onCustomEndChange,
  refreshing = false,
  onRefresh,
}) => {
  const lastUpdated = new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div className="cl-dashboard-header">
      <div>
        <h2 className="cl-section-title">Business Summary</h2>
        <p className="cl-dashboard-header__meta">
          {clientName ? `${clientName} · ` : ''}Updated {lastUpdated}
          {refreshing && <span className="cl-dashboard-header__sync"> · Syncing…</span>}
        </p>
      </div>

      <div className="cl-dashboard-header__actions">
        {period === 'custom' && (
          <div className="cl-dashboard-header__dates">
            <input
              type="date"
              value={customStart || ''}
              onChange={(e) => onCustomStartChange(e.target.value)}
              className="cl-select"
              aria-label="Start date"
            />
            <span className="cl-caption">to</span>
            <input
              type="date"
              value={customEnd || ''}
              onChange={(e) => onCustomEndChange(e.target.value)}
              className="cl-select"
              aria-label="End date"
            />
          </div>
        )}
        <DateRangeDropdown value={period} onChange={onPeriodChange} />
        {onRefresh && (
          <button
            type="button"
            className="cl-btn cl-btn--secondary cl-dashboard-header__refresh"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh dashboard"
          >
            <span className={`material-symbols-outlined${refreshing ? ' cl-spin' : ''}`}>refresh</span>
          </button>
        )}
      </div>
    </div>
  );
};

export default DashboardHeader;
