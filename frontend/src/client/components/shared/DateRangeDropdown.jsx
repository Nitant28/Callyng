import React from 'react';

const DateRangeDropdown = ({ value, onChange, style }) => {
  const options = [
    { label: 'Today', value: 'today' },
    { label: 'Yesterday', value: 'yesterday' },
    { label: 'Last 2 Days', value: '2d' },
    { label: 'Last 3 Days', value: '3d' },
    { label: 'Last 7 Days', value: '7d' },
    { label: 'Last 14 Days', value: '14d' },
    { label: 'Last Month', value: '30d' },
    { label: 'Last Quarter', value: '90d' },
    { label: 'Custom Range', value: 'custom' },
  ];

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="cl-select"
      style={{ height: '48px', minWidth: '160px', ...style }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
};

export default DateRangeDropdown;
