import { useState, useRef, useEffect } from 'react';
import './Dashboard.css';

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
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSelect = (optionValue) => {
    onChange?.(optionValue);
    setOpen(false);
  };

  return (
    <div className="date-range" ref={rootRef}>
      <button
        type="button"
        className="date-range__trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className="material-symbols-outlined date-range__icon">calendar_today</span>
        <span className="date-range__label">{selected.label}</span>
        <span className="material-symbols-outlined date-range__chevron">
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>

      {open && (
        <ul className="date-range__menu" role="listbox">
          {DATE_RANGE_OPTIONS.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                role="option"
                aria-selected={value === option.value}
                className={`date-range__option ${value === option.value ? 'date-range__option--active' : ''}`}
                onClick={() => handleSelect(option.value)}
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

export default DateRangeDropdown;
