import { useState } from 'react';
import './FilterBar.css';

const OUTCOMES = [
  { value: '', label: 'All outcomes' },
  { value: 'Interested', label: 'Interested' },
  { value: 'Not_Interested', label: 'Not interested' },
];

const DURATIONS = [
  { value: '', label: 'Any duration' },
  { value: 'short', label: 'Under 1 min' },
  { value: 'medium', label: '1–3 min' },
  { value: 'long', label: 'Over 3 min' },
];

const FilterBar = ({
  campaigns = [],
  filters,
  onChange,
  onExport,
  onRefresh,
  refreshing,
}) => {
  const [open, setOpen] = useState(false);

  const activeCount = [
    filters.campaignId,
    filters.outcome,
    filters.duration,
    filters.dateFrom,
  ].filter(Boolean).length;

  return (
    <div className="cl-filterbar">
      <button
        type="button"
        className={`cl-filterbar__btn ${open ? 'cl-filterbar__btn--active' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="material-symbols-outlined">tune</span>
        Filters
        {activeCount > 0 && <span className="cl-filterbar__count">{activeCount}</span>}
      </button>

      <button type="button" className="cl-filterbar__btn" onClick={onExport}>
        <span className="material-symbols-outlined">download</span>
        Export
      </button>

      <button
        type="button"
        className="cl-filterbar__btn"
        onClick={onRefresh}
        disabled={refreshing}
      >
        <span className={`material-symbols-outlined ${refreshing ? 'cl-spin' : ''}`}>refresh</span>
        Refresh
      </button>

      {open && (
        <div className="cl-filterbar__panel">
          <label>
            Campaign
            <select
              value={filters.campaignId}
              onChange={(e) => onChange({ ...filters, campaignId: e.target.value })}
            >
              <option value="">All campaigns</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>{c.title}</option>
              ))}
            </select>
          </label>
          <label>
            Outcome
            <select
              value={filters.outcome}
              onChange={(e) => onChange({ ...filters, outcome: e.target.value })}
            >
              {OUTCOMES.map((o) => (
                <option key={o.value || 'all'} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label>
            Duration
            <select
              value={filters.duration}
              onChange={(e) => onChange({ ...filters, duration: e.target.value })}
            >
              {DURATIONS.map((d) => (
                <option key={d.value || 'all'} value={d.value}>{d.label}</option>
              ))}
            </select>
          </label>
          <label>
            From date
            <input
              type="date"
              value={filters.dateFrom}
              onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
            />
          </label>
          {activeCount > 0 && (
            <button
              type="button"
              className="cl-filterbar__clear"
              onClick={() => onChange({ campaignId: '', outcome: '', duration: '', dateFrom: '' })}
            >
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default FilterBar;
