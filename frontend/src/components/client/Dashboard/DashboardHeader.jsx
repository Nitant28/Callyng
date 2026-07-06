import { useState, useRef, useEffect } from 'react';
import './DashboardHeader.css';

export const DATE_RANGE_OPTIONS = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'last2', label: 'Last 2 Days' },
  { value: 'last3', label: 'Last 3 Days' },
  { value: 'last7', label: 'Last 7 Days' },
  { value: 'last30', label: 'Last 30 Days' },
  { value: 'last90', label: 'Last 90 Days' },
  { value: 'custom', label: 'Custom Range' },
];

const DateRangeDropdown = ({ value = 'last7', onChange }) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = DATE_RANGE_OPTIONS.find((o) => o.value === value) ?? DATE_RANGE_OPTIONS[4];

  useEffect(() => {
    const handleClick = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div className="cd-date-range" ref={rootRef}>
      <button type="button" className="cd-date-range__trigger" onClick={() => setOpen((v) => !v)}>
        <span className="material-symbols-outlined">calendar_today</span>
        <span>{selected.label}</span>
        <span className="material-symbols-outlined cd-date-range__chevron">
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {open && (
        <ul className="cd-date-range__menu">
          {DATE_RANGE_OPTIONS.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                className={value === option.value ? 'cd-date-range__option--active' : ''}
                onClick={() => { onChange?.(option.value); setOpen(false); }}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const DashboardHeader = ({ clientName, selectedRange, onRangeChange }) => {
  const name = clientName || 'Client';

  return (
    <header className="cd-header">
      <div className="cd-header__copy">
        <h1 className="cd-header__title">
          Good morning,
          <br />
          {name} 👋
        </h1>
        <p className="cd-header__subtitle">Here&apos;s what&apos;s happening today.</p>
      </div>
      <DateRangeDropdown value={selectedRange} onChange={onRangeChange} />
    </header>
  );
};

export default DashboardHeader;
